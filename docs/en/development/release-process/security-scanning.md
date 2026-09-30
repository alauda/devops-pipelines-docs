---
weight: 30
---

# Running the release security scans

A release needs two security results: a **static** scan of the artifacts and images, and a
**dynamic** scan of the component actually running in a cluster. This guide is how to produce both.

[The release process guide](./index.md#8-security-scanning-static-and-dynamic) defines what counts
as evidence and where it is archived. This guide is the procedure — what to run, in what order, and
which results you are allowed to believe.

## 1. Before you start: do not build this yourself {#1-before-you-start-do-not-build-this-yourself}

Both halves already have an official implementation. A previous round rebuilt the dynamic scan from
scratch by hand and reached four wrong conclusions before the existing pipeline turned up; every one
of them was a case of "I cannot make this work" being mistaken for "this is not covered".

So, before writing any YAML, look in all four places:

1. this documentation set,
2. the release-test repository and its `.tekton` directory,
3. the Pipelines and CronJobs already on the CI clusters,
4. the test platform's own lanes.

If you end up building something anyway, say in the report which of the four you checked.

## 2. The two halves {#2-the-two-halves}

| | Static | Dynamic |
| :--- | :--- | :--- |
| Subject | The artifacts repository: every image a version directory ships | A running deployment of the component |
| Finds | Known CVEs in OS and language packages, secrets, audit findings, configuration problems | Privileged containers, unsafe capabilities, plaintext credentials, host and cluster hardening |
| Driver | `VulnerabilityScan` CRD, plus `image-security-scanner` for individual images | The Ares `security_case` suite |
| How it is run | the `VulnerabilityScan` CRD directly | on CTYun, by the procedure in use since 4.14.0 — see [4.1](#41-where-the-dynamic-scan-runs) |
| Output | An `ImageVulnerabilityReport` and an exported spreadsheet | A report archive per run |

The two are **not** substitutes. A static scan cannot see how the component is deployed, and a
dynamic scan cannot enumerate the CVEs inside an image.

### What no longer counts {#what-no-longer-counts}

- **The security lanes on the Thanos test platform are obsolete.** Do not run them, and do not submit
  their reports as release evidence.
- **The `redline-static-scan-v2` and `redline-runtime-scan` pipelines are no longer used.** The
  static half goes through the `VulnerabilityScan` CRD, the dynamic half through the CTYun procedure
  ([4.1](#41-where-the-dynamic-scan-runs)). Rounds that reference either pipeline are history, not a
  fallback — do not reach for them when the current path gives you trouble.
- **The artifacts repository's `scan-vuln` pipeline is not release evidence either.** Keep using it
  as an early-warning check while fixing vulnerabilities — it is just not what you ship.

## 3. Static scan {#3-static-scan}

### 3.1 Scope: the easiest thing to under-scan {#31-scope-the-easiest-thing-to-under-scan}

`tektoncd-operator` is an OLM operator, so the inventory is **the operator image, the bundle image,
and every image in the CSV's `relatedImages`** — everything needed to actually use the component.
(Cluster Plugins are different: there the inventory is every image listed in the release
`values.yaml`.)

Configuration scanning — Helm charts, Kubernetes manifests and the OLM bundle, checked for pod
security, non-root, privilege, secrets and RBAC — belongs to this stage too.

### 3.2 Run it {#32-run-it}

Create a `VulnerabilityScan` pointing at a version directory of the artifacts repository. The field
that decides the scope is `plugins[].versions[]`, and it takes **the version directory name**, not a
bundle version.

```yaml
apiVersion: security.testing.qa.io/v1alpha1
kind: VulnerabilityScan
metadata:
  name: <a DNS-1123 name, 63 characters or fewer>
  namespace: platform-edge-security         # the only namespace it runs in - see constraint 1
spec:
  target:
    type: ArtifactsRepo
    artifactsRef:
      gitUrl: <artifacts repository>
      commit: <40 lowercase hex characters>   # exactly one of branch / tag / commit
      plugins:
        - name: tektoncd-operator
          versions:
            - v4.15
  dbStrategy:
    mode: Frozen            # a release scan pins the date; see below
    frozenDbTag: <YYYY-MM-DD>
  context:
    productVersion: v4.15.0 # must be non-empty, or the result sync fails
  report:
    enabled: true
    format: xlsx            # the only accepted value
  strategy:
    syncJira: false         # dry run first
  workspaceStorage: 20Gi    # the default is too small for 30+ images
```

**Pin the CVE database date.** `dbStrategy` is two-state: `Frozen` requires `frozenDbTag`, and
`Latest` must not carry one. A release scan uses `Frozen`. Under `Latest` the report records only
the literal string `latest` as its database version and nothing logs the real date, so afterwards
there is no way to prove which database produced the numbers — the result stops being reproducible,
which is the one property a release scan exists to have. Legal values of `frozenDbTag` are tags of
the Trivy database image, written `YYYY-MM-DD` **with dashes** — not `YYYYMMDD`. The current day's
tag is usually not published yet, so the newest available is normally yesterday's. Agree the date
before scanning, not after.

Four constraints that will otherwise cost you an afternoon:

1. **It only runs in `platform-edge-security`**, the namespace owned by the scanner operator
   (Deployment `security-controller-manager`). Project namespaces enforce restricted pod security,
   which blocks the scan worker outright. The symptom looks like an RBAC problem and is not one.
2. **Never pre-create the ServiceAccount, Role or RoleBinding.** The operator creates them and
   refuses to adopt objects it did not create; a hand-made one leaves the scan in `Pending` with no
   PipelineRun at all. Delete them and it recovers in seconds.
3. **`kubectl auth can-i` lies under a token-proxy context** — it answers `no` for everything. Use
   `kubectl apply --dry-run=server` to find out whether you may create the resource.
4. **Task pods are reclaimed about ten minutes after they succeed**, and the TaskRun does not keep
   their results. Stream logs to a file while the scan runs; do not plan to fetch them afterwards.

The quickest way to get the rest of the spec right is to read a live one: the platform runs its own
scheduled scans in that namespace, so `kubectl -n platform-edge-security get vulnerabilityscan` gives
you working examples. Copy everything from them **except `dbStrategy`** — they all run `Latest`, which
is the one setting a release scan must not use.

For individual images, `image-security-scanner` is the source of truth. Its scan types are `audit`
(debug and cracking tools, sensitive scripts, login-capable non-root users, UID/GID 0 non-root
users, sudoers entries, unexpected shells and package managers), `vuln` (OS and language packages
plus secrets), `virus`, or `all`. It reads layers over the registry API, so no container runtime is
needed.

### 3.3 Read the result {#33-read-the-result}

**`ImageVulnerabilityReport.status.summary` is always an empty object.** Reading it the way the
tooling documentation suggests reports zero vulnerabilities on every scan. Take the numbers from the
exported spreadsheet, and ship that spreadsheet as-is — do not assemble one by hand.

## 4. Dynamic scan {#4-dynamic-scan}

### 4.1 Where the dynamic scan runs {#41-where-the-dynamic-scan-runs}

**Since 4.14.0 the dynamic scan is run on CTYun, by a procedure that replaced the earlier one
outright.** Anything written for a release before 4.14.0 — the `redline-runtime-scan` pipeline
included — describes the old arrangement and no longer applies. It is not a fallback either: if the
current procedure gives you trouble, the answer is to fix that, not to revive a retired pipeline.

> **This page does not describe that procedure yet.** It is not written down anywhere this guide can
> cite, so rather than guess it is left as a gap. Ask the DevOps team where the current round runs
> and how it is triggered before you start — and write the answer in here, so that the next person
> does not have to ask the same question.

What the rest of this section is good for: the evidence archived for 4.14.0 is a single
`security-runtime-ares-<id>.tar.gz`, so the suite behind the CTYun procedure is still Ares. How the
suite is run ([4.2](#42-if-you-drive-ares-directly)) and the reading rules in
[4.3](#43-read-the-result-the-trap-that-matters-most) come from completed rounds of that suite and
still describe it — they are what to fall back on when you have to drive it yourself.

### 4.2 If you drive Ares directly {#42-if-you-drive-ares-directly}

Sometimes you have to drive the suite yourself — against an environment the standard round cannot
reach, or to reproduce a finding.

**What you are launching.** The suite is one image,
`152-231-registry.alauda.cn:60070/automation/ares:master`. Its entrypoint script ends in
`python3 main.py`, the cases are Python files under `/app/security_case/` inside the image, and
`TESTCASES` selects what runs — `security_case` for the whole suite, or a path down to a single file
such as `security_case/cis_scan/test_k8s_cis.py`. `DEBUG_TEST=true` skips the fixed ten-second sleep
the entrypoint starts with. Everything else is configuration, and configuration is **plain
environment variables** — no prefix, no config file.

That is why there are two shapes of the same thing:

1. **A task in the test platform's test YAML**, which is how a standard round gets it: a
   `category: api` task running that image, with the variables under `envs`. Use this wherever the
   automation workflow covers the environment.
2. **A Pod or container you start yourself**, with the same variables in its environment. Mount the
   node SSH key in and point `VM_KEY` at the mounted path. Two of the API cases additionally need a
   Swagger file mounted at `/app/test_data/security/apis-swagger.json` — ask the product team to
   generate it.

The template for shape 1, and the full variable list both shapes share, are in
`builders/skills/builders-alauda-security-scan/references/security-test-content.md` of the builders
repository ([section 9](#9-where-the-details-live)). The variables that decide whether a run is
usable at all:

| Variable | What to put in it |
| :--- | :--- |
| `API_URL` | API address of the target platform |
| `REGISTRY` | registry address |
| `REGION_NAME` / `GLOBAL_REGION_NAME` | the target cluster / the global cluster |
| `USERNAME` / `PASSWORD` | platform account — **read from a Secret, never inline** |
| `TESTCASES` | `security_case` |
| `NAMESPACE_OF_SCAN` | the namespaces your component owns |
| `RESOURCE_PREFIX` | prefix for the resources the round creates |
| `WORKER_NUM` | parallel workers; `1` unless you have a reason |
| `VM_KEY` | path the node SSH **key** is mounted at — this is how you authenticate to nodes |
| `PLUGINS_LIST` | JSON list of `plugin_names` / `plugin_version` — a filter, see below |
| `ARTIFACT_GIT_ADDRESS`, `SECURITY_BRANCH`, `SECURITY_GITLAB_*` | only needed when the suite has to generate the image inventory itself, see below |
| `JIRA_SERVER`, `JIRA_USER`, `JIRA_PWD`, `DEFAULT_ISSUE_*` | issue filing; all three `JIRA_*` must be set together or filing is silently skipped |

`NAMESPACE_OF_SCAN` and `PLUGINS_LIST` are JSON written into a string — `'["ns-a","ns-b"]'` shaped,
not comma-separated.

**Never set the node password variable.** The task template carries `VM_PASSWORD` next to
`VM_KEY_CONTENT`; leave it empty and use the key. In one round a node's root password was passed in
as a container environment variable, and the suite's own "sensitive data in container environment"
case found it and wrote it into the report in plaintext. The password had to be rotated. Nothing in
the suite needs that variable — authenticate to nodes with a key.

Three more things that are easy to get wrong:

- **The image inventory file is a derived artifact** and is not in the repository. The suite skips
  generating it if it already exists, which is also the way to run without repository credentials.
- **The plugin list is a filter, not metadata.** Leave it out and every finding is skipped with a
  message about needing a plugin list.
- **Verify the login by hand once before batch runs.** The retry logic will trip the platform's
  captcha after three failures, and the login flow does not handle captchas.

### 4.3 Read the result — the trap that matters most {#43-read-the-result-the-trap-that-matters-most}

**This suite reports false green.** The runner uses rerun-on-failure, so a case that fails the first
time and passes on a retry is recorded as a pass; the failed-case file ends up empty and the exit
code is zero.

**Judge the run from the first execution's test summary, not from the exit code or the failed-case
file.** Trusting the exit code here is self-deception.

When you do have findings, two more things separate real ones from noise:

- **Anchor each finding to its container / pod / namespace triple.** Splitting the report on
  whitespace will paste one namespace's payload onto another's pod — a good way to accuse your own
  component of leaking credentials it never touched.
- **Exclude self-contamination and keyword false positives.** The scanner's own pods appear in the
  results, and any value containing a word like `token` matches regardless of what it holds.
- **Some assertions are cluster-wide even when you scope the namespaces.** A few cases ignore the
  namespace setting and assert across the whole cluster, so somebody else's workload can fail your
  run. Check the scope of a case before treating its finding as yours.

A clean result reads like this: every non-passing case is accounted for as a framework defect, a
configuration gap, an air-gap restriction, a cluster-wide assertion that matched someone else's
resource, or a keyword false positive — **and you say which, case by case**. "No findings" without
that breakdown is not a result.

## 5. Exemptions {#5-exemptions}

Findings that will not be fixed are registered as exemptions rather than edited out of the report.
Two properties of that registry cause trouble:

- **Exemptions are recorded per plugin and per branch, and do not carry across branches.** Something
  exempted on an older release branch is absent on the new one, and the pipeline will report every
  finding as unregistered.
- When the unfixed-findings file and the total-findings file are the same size, nothing is
  registered at all — that is the signal, not an error message.

Register exemptions through the exemption API, **not** by editing markdown in the release-test
repository.

> The exemption flow still runs on the Thanos platform, which is otherwise obsolete. Confirm the
> current path before filing rather than assuming either way.

## 6. Archive both halves {#6-archive-both-halves}

Both results go to the release-test repository, next to the regression reports:

```text
plugins/tektoncd-operator/<vX.Y>/Test_Reports/<vX.Y.Z>/security/
```

- the dynamic run's report archive,
- the static scan's exported spreadsheet.

**Archive as you go.** Report URLs point at a server whose retention nobody on this side controls,
and the pods that produced them are reclaimed within minutes.

## 7. Traps, in one place {#7-traps-in-one-place}

| Symptom | Real cause |
| :--- | :--- |
| Dynamic scan exits zero with an empty failed-case file | Rerun-on-failure turned first-attempt failures into passes — read the first run's summary |
| Static scan stuck in `Pending`, no PipelineRun | Someone pre-created the ServiceAccount / Role / RoleBinding |
| Static scan will not start in your own namespace | Restricted pod security blocks the worker; use the security namespace |
| `auth can-i` says you have no permissions at all | It is wrong under a token-proxy context; use `--dry-run=server` |
| Report claims zero vulnerabilities | `status.summary` is always empty; read the spreadsheet |
| Every finding shows as unregistered | Exemptions are per-branch and were never carried over |
| Findings implicate your component but the resources are unfamiliar | Cluster-wide assertions, scanner self-contamination, or keyword matches |
| Logs or results gone when you go to collect them | Pods are reclaimed minutes after success; stream to a file during the run |

## 8. What a completed round looks like {#8-what-a-completed-round-looks-like}

From one release line, as a sense of scale and of what "clean" means:

- **Static**: 32 images scanned, a single finding at unknown severity, nothing that had to be fixed.
- **Dynamic**: no real findings attributable to the component; every non-passing case classified,
  with a handful of cases uncovered because credentials for external systems were unavailable —
  **stated explicitly rather than counted as passes**. That round predates the move to CTYun
  ([4.1](#41-where-the-dynamic-scan-runs)), so read it for the shape of a clean result, not for how
  the scan is run today.

Both halves archived, and the report says what was **not** covered.

## 9. Where the details live {#9-where-the-details-live}

This guide is the procedure. When you need the field-by-field detail behind a step, these are the
sources it was written from — and the four places [section 1](#1-before-you-start-do-not-build-this-yourself)
tells you to check before building anything yourself.

**Static half — the `VulnerabilityScan` CRD.** In the builders repository
`https://gitlab-ce.alauda.cn/alauda-ai/alauda-ai-builders`:

- `builders/skills/builders-vulscan-artifacts/SKILL.md` — creating, inspecting, rerunning and
  cleaning up a scan.
- `builders/skills/builders-vulscan-artifacts/references/create-templates.md` — spec templates.
- `builders/skills/builders-vulscan-artifacts/references/inspect-recipes.md` — how to read a run
  while it is still alive.
- `builders/skills/builders-vulscan-artifacts/references/strategy-fields.md` — `strategy` semantics,
  including the cutoff and threshold fields that decide Jira filing. Read it before turning
  `syncJira` on.

**Dynamic half — the Ares suite.** Same repository:

- `builders/skills/builders-alauda-security-scan/references/security-test-content.md` — the case
  list with its levels and case IDs, the dynamic-scan task template quoted in
  [4.2](#42-if-you-drive-ares-directly), the full environment-variable list, and the manual CIS and
  STIG scopes.
- `builders/skills/builders-alauda-security-scan/references/security-scan-workflow.md` — where the
  scan sits in the release workflow.

**The artifacts repository** `https://code.alauda.io/alauda-pipelines/engineering/artifacts`, for
everything around the version directory this guide scans:

- `docs/how_to_run_vuln_scan.md` — `extra_settings.yaml` and `vuln_reviewed.yaml`, the exemption
  registration rules used by [section 5](#5-exemptions), and the fix-or-exempt criteria.
- `docs/scan_vuln_pipeline_design.md` and `docs/scan_artifact.md` — the `scan-vuln` and
  `scan-artifact` pipelines, which are development aids and **not** release evidence
  ([section 2](#2-the-two-halves)).
- `docs/directory_structure.md` — what a version directory is, which is what
  `plugins[].versions[]` names.

**In this repository**: [the release process guide](./index.md#8-security-scanning-static-and-dynamic)
defines what counts as evidence and where it is archived.
