---
created: '2026-09-16'
updated: '2026-09-16'
weight: 50
---

# Release Process

This guide is for the engineer who has to drive a `tektoncd-operator` release — or to pick up one
segment of it. When you are done reading you should be able to answer: **what are the steps between
source code and "an offline package a customer can install, plus a passing release-test report",
how is each step triggered, and what proves that it actually succeeded.**

Pipeline names, parameters and trigger syntax in this guide come from the real files under
`.tekton/` in this repository and from the shared catalog pipelines. Items marked "not verified"
are exactly that — do not treat them as facts.

Access credentials (kubeconfig for the build cluster, platform accounts) are not in this guide by
design: ask the DevOps team for them. Every command below assumes you have already selected the
build cluster context.

**Start here.** This page is the entry point for a release: it carries the whole chain, what
triggers each step and what proves it worked. Three companion guides hold the long procedures, and
each is linked from the stage that needs it — you should not have to go looking for them:

| Guide | When you open it |
| :--- | :--- |
| [Build a Release-Test Environment by Hand](./release-test-environment.md) | Stage G, when the tier you need is env5 or a shape the built-in templates do not give you |
| [Running the env5 Regression by Hand](./env5-manual-regression.md) | Stage G, once that environment exists — env5 is never covered by the automated batch |
| [Running the Release Security Scans](./security-scanning.md) | Stage H, for the static and dynamic scan procedures |
| [Release Review and Closeout](./release-review-and-closeout.md) | The non-functional gate, release review evidence and post-publication closeout |

## 1. The whole chain on one page

A release spans **twelve publication stages plus one cross-cutting gate**. The first five turn code
into an installable package, the next three prove the package is good, stage I turns it into the
official deliverable, and the last three publish it. The N gate runs between H and I — the release
is not over when the package exists.

| Stage | What it does | Repository | How to trigger | What proves it worked |
| :--- | :--- | :--- | :--- | :--- |
| **A** | Bump every sub-component to its latest build | operator | `/test to-update-components branch:<branch>` | A `chore/update-components-*` MR appears |
| **B** | Produce the bundle build | operator | Automatic once A's MR is merged | A new tag such as `v4.15.0-rc.302.gdbf0be2` |
| **C** | Record that tag in the artifacts ledger | artifacts | Create an `artifacts-versions-sync` run, or edit `versions.yaml` by hand | A `sync/tektoncd-operator-<branch>` MR |
| **D** | Regenerate the lock, scan for CVEs | artifacts | `artifacts-update` is automatic; `scan-vuln` must be triggered | Bot's `[ci skip]` commit + a vulnerability report comment |
| **E** | Build the offline packages | artifacts | Comment `/package plugins=tektoncd-operator` on the MR | Three `.tgz` files uploaded to S3 |
| **F** | Write the release notes | operator | Edit four documentation files, open an MR | `doc-build` is green and the site publishes |
| **G** | Release testing | operator | `/test to-release-test branch:<branch> …` | An Allure report per tier **and** per supported ACP minor, archived in the release-test repository |
| **H** | Security scanning (static + dynamic) | QA security tooling | See [Security scanning](#8-security-scanning-static-and-dynamic) | Static xlsx + dynamic Ares results + the evidence checklist, archived in the release-test repository |
| **N** | Non-functional gate | release-test | See [Release Review and Closeout](./release-review-and-closeout.md) | High Availability, Performance and Stability each have a new report, approved reuse decision or owner-confirmed not-applicable outcome |
| **I** | Repackage under the final version number | operator + artifacts | Tag → build → update the ledger → `/package` | `…v4.15.0.tgz` with no `rc` suffix |
| **J** | Sync the packages to the mirrors | mirrors | The sync API — see [10.1](#101-stage-j-sync-the-packages-to-the-mirrors) | The new version is visible in the package mirror |
| **K** | Register the version for Alauda Cloud | devops-artifact | Open a PR under `released-artifacts/tektoncd-operator/<minor>/` | The PR — **keep its number**, stage L needs it |
| **L** | Publish to Alauda Cloud | devops-artifact + Alauda Cloud | Run the `upload-ac` pipeline with `revision: pull/<K's PR>/head` | The version is **reviewed and listed** on Alauda Cloud |

**F and G do not depend on each other** and can run in parallel. **G depends on E** (a package must
exist) and **E depends on D** (the version must be recorded in the ledger). **N is a cross-cutting
gate between H and I**; it may run in parallel with G and H, but it must be closed before I.
**I, J, K and L are strictly sequential**, and the chain only ends at a human approval: stage L's
pipeline going green means the artifact was uploaded, not that the release is published.

## 2. Things to know before you start

### 2.1 Three repositories

| Repository | URL | Role |
| :--- | :--- | :--- |
| operator | `https://code.alauda.io/alauda-pipelines/tektoncd-operator` | Source code, every pipeline under `.tekton/`, the release notes |
| artifacts | `https://code.alauda.io/alauda-pipelines/engineering/artifacts` | The artifact ledger (which version is which digest) and the packaging entry point |
| catalog | `https://code.alauda.io/platform-edge/pipelines/catalog-incubator` | The shared pipelines themselves (release testing and packaging are implemented here) |
| devops-artifact | `https://github.com/AlaudaDevops/devops-artifact` | What Alauda Cloud is fed from. Used only at the end, in [stage K](#102-stage-k-register-the-version-in-devops-artifact) |

> **Two artifact repositories, and they are not the same thing — do not mix them up.** The GitLab
> `artifacts` repository is where a release is built and packaged from: stages C, D, E and I. The
> GitHub `devops-artifact` repository is where a finished release is registered so that Alauda Cloud
> can publish it: stage K only. Commands and semantics do not carry over between them — tell them
> apart by where you are opening the change.

### 2.2 Where the pipelines run

```text
cluster     edge-build
namespace   alauda-pipelines-build      <- always pass -n explicitly
console     https://alauda-edge.alauda.io/console-acp/workspace/alauda-pipelines~edge-build~alauda-pipelines-build/pipeline/pipelineRuns/detail/<run>
```

The two queries you will use constantly:

```bash
NS=alauda-pipelines-build

kubectl -n $NS get pipelinerun <run> \
  -o jsonpath='{.status.conditions[0].status}{" "}{.status.conditions[0].reason}{" "}{.status.conditions[0].message}{"\n"}'

kubectl -n $NS get taskrun -l tekton.dev/pipelineRun=<run> \
  -o custom-columns='TASK:.metadata.labels.tekton\.dev/pipelineTask,STATUS:.status.conditions[0].reason'
```

### 2.3 The one trigger syntax

```text
/test <pipeline-name> branch:<branch> [key=value ...]
```

It works in an MR comment and in a commit comment. When you trigger from a commit — especially for a
release branch — **`branch:` is mandatory**.

Two exceptions, both parameterised commands rather than plain re-triggers:

| Command | Only valid in | Purpose |
| :--- | :--- | :--- |
| `/package plugins=<plugin> [build_archs=…]` | an **open MR comment** in the artifacts repository | Build the offline packages. Posting it on a commit is rejected by PaC |
| `/upgrade-test from=<branch> [to=<branch>]` | a PR/MR comment in the operator repository | Upgrade smoke test, see [Upgrade testing](#78-upgrade-testing) |

Do not invent or reuse any other custom comment token.

### 2.4 "The pipeline is red" does not mean "this step failed" {#24-the-pipeline-is-red-does-not-mean-this-step-failed}

This comes up again and again. The technique is always the same: **look at the taskRun level and
find which task is actually red**.

| What you see | What it really means |
| :--- | :--- |
| `tektoncd-operator-build` failed but only `image-scan` is red | The artifacts were pushed; you can continue. `image-scan` is an image CVE gate |
| `scan-vuln` failed but only `gate` is red | Scanning, reporting and commenting all succeeded; the CVE threshold gate tripped |
| `artifacts-package` failed but the logs show every package uploaded | The Tekton result exceeded 4096 bytes, see [Stage E](#6-stage-e-build-the-offline-packages) |
| `auto-translate-*` shows `FailureIgnored` in a doc build | By design, it does not fail the run; something else killed it |

### 2.5 Two standing rules

- **Open MRs, do not merge them yourself.** A human reviews and merges at every stage.
- **Cancel runs with `CancelledRunFinally`, never `Cancelled`** — the latter skips the finally
  clause, so environments and other resources are never released:

  ```bash
  kubectl -n alauda-pipelines-build patch pipelinerun <run> \
    --type=merge -p '{"spec":{"status":"CancelledRunFinally"}}'
  ```

## 3. Stage A: bump the sub-components

The bundle ships a dozen or so components (pipeline, triggers, chains, results, pac, pruner, MAG and
friends). Bring them all up to date first:

```text
/test to-update-components branch:release-4.15
```

- `branch` only accepts `main`, `master` or `release-*`; anything else makes the pipeline fail on
  purpose.
- **Output**: a `chore/update-components-<branch>` MR.
- **Checkpoint**: a human reviews and merges. Skim the diff first and confirm the bumped versions
  are the ones you expect.

## 4. Stage B: produce the bundle build

Merging A's MR pushes to the target branch, which automatically triggers `tektoncd-operator-build-*`.

- **Why you must wait for it**: stage C synchronises "the newest build of that branch". Running C
  before the build finishes synchronises the old tag and wastes the whole round.
- **Done when**: a new tag exists, shaped like `v4.15.0-rc.302.gdbf0be2`
  (`version-rc.<commits>.g<short sha>`).
- If only `image-scan` is red you can continue; see [2.4](#24-the-pipeline-is-red-does-not-mean-this-step-failed).

## 5. Stage C and D: record the version, then scan it

### 5.1 Stage C — write the tag into the ledger

Create an `artifacts-versions-sync` PipelineRun on the build cluster with `dryRun=false`.

> **Release branches must pass `operatorBranch` explicitly.** It defaults to `main`, and forgetting
> it means "only the main line was synchronised, your release branch never moved" — while the
> pipeline stays green. This is the most silent way to waste a round.

**Done when**: the run succeeds and its `mergerequest-url` result points at a new
`sync/tektoncd-operator-<branch>` MR with `changed=1`.

Editing `released-artifacts/tektoncd-operator/<vX.Y>/versions.yaml` by hand and opening an MR has the
same effect and is a perfectly good alternative.

### 5.2 Stage D — `artifacts-update` (automatic)

Any push to the MR triggers it. It regenerates `artifacts.yaml`: tags are resolved to digests and the
list of included images is expanded.

The durable proof of success is that Alauda Bot appends a commit to the MR:

```text
chore(artifacts): regenerate locks [ci skip] - alauda-pipelines-build/artifacts-update-<hash>-commit
```

**The MR head moves to that bot commit.** Packaging must wait until the head is that commit,
otherwise you package the old `artifacts.yaml`.

While you are there, check `artifacts.yaml`: the `version`/`tag` are the ones you want, the `digest`
matches the build output, and the component versions under `includes` look right.

### 5.3 Stage D — `scan-vuln` (you must trigger it) {#53-stage-d--scan-vuln-you-must-trigger-it}

**A trap worth memorising**: the bot's commit carries `[ci skip]`, so PaC skips that head entirely and
**`scan-vuln` never runs by itself**. The tell is that the commit statuses for the head contain no
`scan-vuln` entry at all.

```text
/test scan-vuln version=v4.15
```

- **Output**: a vulnerability report comment on the MR plus an HTML/JSON report uploaded to S3.
- The authoritative count is `Total non-waived vulnerabilities: N` in the full comment body; the
  first few table rows are truncated and will mislead you.
- If only the `gate` task is red, the scan worked and the threshold tripped — the pipeline is not
  broken.

> This scan is **our own early-warning tool**. It is not the security evidence a release ships with;
> see [Security scanning](#8-security-scanning-static-and-dynamic).

## 6. Stage E: build the offline packages {#6-stage-e-build-the-offline-packages}

Comment on the **open MR** in the artifacts repository:

```text
/package plugins=tektoncd-operator
```

| Parameter | Default | Notes |
| :--- | :--- | :--- |
| `plugins` | none, **required** | Directory name under `released-artifacts/`, e.g. `tektoncd-operator` |
| `build_archs` | `amd64,arm64,ALL` | Omit it and all three variants are built. `ALL` is one package containing both architectures |

Measured output for `v4.15.0-rc.302.gdbf0be2`:

```text
tektoncd-operator.latest.amd64.v4.15.0-rc.302.gdbf0be2.tgz    662,974,764 B  (~632 MiB)
tektoncd-operator.latest.arm64.v4.15.0-rc.302.gdbf0be2.tgz    600,451,924 B  (~573 MiB)
tektoncd-operator.latest.ALL.v4.15.0-rc.302.gdbf0be2.tgz    1,241,273,500 B  (~1.16 GiB)
```

Download URLs look like:

```text
https://zos-view-cd.alaudatech.net:9002/platform-edge-alauda-pipelines-packages/tektoncd-operator/rc/<file>
```

The `rc` path segment follows the version phase: `rc` to `/rc/`, beta to `/beta/`, hotfix to
`/hotfix/`, PR builds to `/pr/`.

Release testing needs a **second** package out of the same repository — the e2e image set — and this
pipeline does not build it. See [6.3](#63-the-second-package-tektoncd-operator-e2e).

### 6.1 Every package built and uploaded, pipeline still red {#61-every-package-built-and-uploaded-pipeline-still-red}

The `package-artifacts` step fails **after every package has been built and uploaded**, with:

```text
ERROR Error while substituting step artifacts:
error="Termination message is above max allowed size 4096, caused by large task result."
```

**Cause**: packtool walks **every version line** under the plugin directory (v4.2, v4.6, v4.12, v4.14,
v4.15 were all built in one measured run) across three variants and several channels, and writes all
of the resulting URLs into a single task result, which blows past Tekton's 4096-byte termination
message limit.

**How to tell the package is fine**: find these three lines for your version in the log.

```text
successfully packaged and saved it to: .../tektoncd-operator.latest.ALL.<version>.tgz
uploading plugin tektoncd-operator channel latest to s3 tektoncd-operator/rc/<file>
compute checksum for file ..., size: <bytes>, in time: <seconds>
```

**The price**: the `binary-artifacts-url` result is lost, so you have to assemble the download URL
from the rule above.

### 6.2 Packages you did not ask for

packtool also builds any other version under that plugin directory that has been bumped but never
packaged. Note those as incidental in your report so nobody thinks you shipped something extra.

### 6.3 The second package: `tektoncd-operator-e2e` {#63-the-second-package-tektoncd-operator-e2e}

Stage E builds the package a customer installs. Release testing needs a **second** package out of
the same artifacts repository: `tektoncd-operator-e2e`, the offline delivery unit for the e2e test
image plus the supporting images the suite deploys (busybox, postgres, gitlab-ce). An air-gapped
environment cannot pull those from `registry-dev.alauda.io`, so they have to arrive as a `.tgz` and
be pushed into the platform registry.

**`/package plugins=tektoncd-operator-e2e` does not build it.** That directory carries no
`metadata.yaml` / `versions.yaml`, only a hand-written Violet `PackageManifest` and a digest lock,
and packtool regenerates its own manifest from the bundle declared in those two files — it would
ignore the hand-written one. A dedicated pipeline calls `violet package <version-dir>` directly
instead: `.tekton/pipelines/package-e2e-artifact.yaml` in the artifacts repository.

**Step 1 — record the image set.** Under `released-artifacts/tektoncd-operator-e2e/vX.Y/`, update
two files together and open an MR:

| File | What it holds |
| :--- | :--- |
| `manifest.yaml` | `spec.artifact` = the commit-specific test image from [7.3](#73-step-1--build-the-e2e-test-image); `spec.relatedImages` = the supporting images; `spec.version` = what names the package |
| `images.lock.yaml` | The expected source manifest digest of every image above, in the same order (`crane digest <reference>`) |

**Step 2 — build it.** Comment on that MR, or on a commit:

```text
/test artifacts-package-e2e branch:<branch>
```

The run probes S3 first and builds only the versions whose `.tgz` is not there yet, so re-running is
cheap and a run normally packages just the version your MR touched. To rebuild a version that was
already published, bump `spec.version` — the object key contains it, so an unchanged version is
always treated as "already uploaded".

One multi-arch package per version directory (amd64 and arm64 in one file; measured 6,362,975,018 B
for `v4.10.2` and 6,583,164,697 B for `v4.13.0-alpha.6`):

```text
https://zos-view-cd.alaudatech.net:9002/platform-edge-alauda-pipelines-packages/tektoncd-operator-e2e/<vX.Y>/tektoncd-operator-e2e.ALL.<spec.version>.tgz
```

Mind the key: this package is filed under its **minor directory**, not under a release phase — there
is no `/rc/` segment like the plugin packages in [6](#6-stage-e-build-the-offline-packages). A
manual or air-gapped run fetches it from a package mirror rather than from S3
(`http://package-minio.alauda.cn:9199/packages/tektoncd-operator-e2e/<vX.Y>/<file>`), so it has to be
synced there like any other package — [stage J](#101-stage-j-sync-the-packages-to-the-mirrors).

**Trap: `Digest drift`.** Every image is digest-verified against `images.lock.yaml` both before and
after packaging, and the packaged closure is read back out of the `.tgz` and compared with the
manifest. Because the manifests pin mutable tags (`:latest`, `:16`), a rebuilt upstream image makes
the run fail with `Digest drift`. Refresh the lock with `crane digest <reference>`; do not weaken
the check.

**Pushing it is not like pushing the plugin.** It is an image-only unit, so it goes up with
`violet push --skip-crs` and must not create `ModulePlugin` / `ModuleConfig` resources. The push and
its verification are written out in
[Running the env5 regression by hand](./env5-manual-regression.md#5-get-the-e2e-package-into-the-environment);
the directory layout and the rules for adding a version line live in that artifact's own
`released-artifacts/tektoncd-operator-e2e/README.md`.

## 7. Stage F and G: prove the package is good

### 7.1 Release notes

Four files under `docs/en/`:

| File | What changes |
| :--- | :--- |
| `overview/release_notes.mdx` | A new `## vX.Y.Z` section; the maintenance window and the compatibility matrix |
| `overview/lifecycle_policy.mdx` | One lifecycle row (dates, LTS or not) |
| `upgrade/upgrade_path.mdx` | The upgrade path table for this version |
| `overview/feature_maturity.mdx` | Maturity of new features (Alpha / Beta / GA) |

The nicest part: Fixed Issues and Known Issues are not written by hand. They are placeholders:

```text
{/* release-notes-for-bugs?template=…&version=v4.15.0 */}
```

The documentation build pulls them from Jira by `fixVersion`, so you only update the version number.

**But there is a gate**: the JQL in `doom.config.yml` requires `ReleaseNotesStatus = Publish`. An
issue that is Done but whose field is not `Publish` **will not appear**. So "Fixed Issues is empty" is
usually a Jira field problem, not a documentation problem.

- **Local check**: `yarn lint`.
- **CI**: `doc-build-alauda-devops-pipelines`. Inside it `auto-translate-*` is allowed to fail; the
  task that actually fails the run is `check-translations`, which is designed to say "translation did
  not finish cleanly, so the site is not built from this run". Read that task's log, not the
  translation tasks'.

### 7.2 Release testing: what it is

**Release testing runs the product e2e suite against the artifact a customer actually installs, on a
real ACP environment.** It is a different thing from the vcluster lane:

| Lane | Subject | Environment | Installation |
| :--- | :--- | :--- | :--- |
| `to-e2e-vcluster` | the **code** (`release.yaml`) | a vcluster it creates | `kubectl apply` |
| `to-release-test` | the **deliverable** (offline package) | a real ACP | violet package to regional S3, then an **OLM Subscription** |

### 7.3 Step 1 — build the e2e test image {#73-step-1--build-the-e2e-test-image}

```text
/test to-e2e-vcluster branch:release-4.15
```

**Do not trigger `to-build-operator-e2e-image`.** That lane only produces the `:base` tooling layer
and will never contain the `testing/` code. The image with the scenarios is produced by the
`build-test-image` task inside the e2e lane.

Wait for that one task only (a few minutes), not the whole lane (hours):

```bash
kubectl -n $NS get taskrun \
  -l "tekton.dev/pipelineRun=<your to-e2e-vcluster run>,tekton.dev/pipelineTask=build-test-image" \
  -o jsonpath='{range .items[*]}{range .status.results[*]}{.name}={.value}{"\n"}{end}{end}'
# IMAGE_URL = registry-dev.alauda.io/alauda-pipelines/tektoncd-operator-e2e/operator-e2e:v4.15.0-rc.307.ge6ea9cf
```

**Always use that commit-specific tag, never the floating tag (`:release-4.15`) pushed alongside it.**
The test-image package is cached on the sha256 of its manifest file, and the manifest records the
**tag string, not the digest** — so rebuilding the same floating tag leaves the manifest byte for byte
identical, the package is reused, and **the environment keeps running the old image**.

An air-gapped environment cannot pull this image at all — it has to reach the platform registry
inside the `tektoncd-operator-e2e` package, which is built separately:
[6.3](#63-the-second-package-tektoncd-operator-e2e).

### 7.4 Step 2 — where the two mandatory parameter values come from

`to-release-test` has two "sentinel" parameters. Getting them wrong either fails the run outright or,
worse, tests the wrong thing.

**`release_test_plugin_version` — the package under test.** It must already be recorded on `main` in
the artifacts ledger (that is, stage D is merged). Read it, do not copy it from memory:

```bash
glab api --hostname code.alauda.io \
  "projects/alauda-pipelines%2Fengineering%2Fartifacts/repository/files/released-artifacts%2Ftektoncd-operator%2Fv4.15%2Fversions.yaml/raw?ref=main"
# latest: v4.15.0-rc.302.gdbf0be2      <- this value
```

**`release_test_test_image` — the image that runs the scenarios.** Copy `IMAGE_URL` from the
`build-test-image` result in step 1. Never assemble it by hand.

#### The two version numbers are not supposed to match

Almost everybody stumbles here: the package is `rc.302.gdbf0be2` while the image is
`rc.307.ge6ea9cf`, which looks like a mistake. They are different artifacts produced by different
lanes:

| | `release_test_plugin_version` | `release_test_test_image` |
| :--- | :--- | :--- |
| What it is | the **subject**: the package a customer installs | the **tool**: the image holding the scenarios |
| Where the version comes from | the tag of that **build**, as recorded in the ledger | the git version of the **branch head** when the e2e lane was triggered |
| When it changes | only when a new bundle is built | on any commit to the branch, **including documentation-only ones** |

So the gap between them is often nothing but a few documentation commits, and "the ledger only has
302, not 307" is entirely normal — 307 was never a package version.

What you actually verify is not that the numbers match, but that the package version is the one you
are releasing and that the image contains the scenario code you want to exercise.

### 7.5 Step 3 — trigger the tiers

For env2, env4 and env6 (CTYun, direct connection):

```text
/test to-release-test branch:release-4.15 release_test_env_type=env2 release_test_plugin_version=v4.15.0-rc.302.gdbf0be2 release_test_test_image=registry-dev.alauda.io/alauda-pipelines/tektoncd-operator-e2e/operator-e2e:v4.15.0-rc.307.ge6ea9cf
```

For env1, env3 and env5 (IDC — **the SOCKS proxy is mandatory**):

```text
/test to-release-test branch:release-4.15 release_test_env_type=env1 release_test_target_proxy_url=socks5h://ssh-socks5-proxy.alauda-pipelines-catalog-build.svc.cluster.local:1080 release_test_plugin_version=v4.15.0-rc.302.gdbf0be2 release_test_test_image=registry-dev.alauda.io/alauda-pipelines/tektoncd-operator-e2e/operator-e2e:v4.15.0-rc.307.ge6ea9cf
```

**The tier name decides which region the package is mirrored to** — it is hard-coded in the catalog
by slot name:

```text
env1 / env3 / env5  ->  destination=idc     (env1 arm, env3 hybrid, env5 x86-intl)
env2 / env4 / env6  ->  destination=ctyun   (x86)
```

Forgetting the proxy shows up as a sync stage that takes tens of minutes, with
`target_probe_proxy=disabled` and `target probe unavailable … reason=transport-28 action=full-sync`
in the log. When it is set correctly you see
`target_probe_proxy=enabled probe_proxy_source=parameter`.

### 7.6 Coverage: how many rounds a release actually needs

This is scope, not an option. Two dimensions have to be covered.

**Dimension one — the six tiers. All of them.**

| Tier | Region | Shape | SOCKS proxy | Notes |
| :--- | :--- | :--- | :--- | :--- |
| env1 | IDC | arm (intl installer) | **yes** | |
| env2 | CTYun | x86 | no | |
| env3 | IDC | hybrid | **yes** | |
| env4 | CTYun | x86 | no | |
| env5 | IDC | x86 (intl installer) | **yes** | **Not part of the automated batch — someone has to trigger it by hand**; the procedure is [Running the env5 regression by hand](./env5-manual-regression.md) |
| env6 | CTYun | x86 on MicroOS | no | **Also mandatory** |

Finishing env1 to env4 is not the end of it. Either all six have reports, or you state explicitly
which tier was skipped and why.

env5 having to be triggered by hand usually also means standing the environment up by hand — see
[Build a Release-Test Environment by Hand](./release-test-environment.md).

**Dimension two — the ACP platform version.**

A release must be regressed on the newest ACP **and at least once on every ACP minor still in
support**. The supported range is whatever that version's compatibility matrix in the release notes
declares — for example v4.15.x declares ACP 4.0, 4.1, 4.2, 4.3 and 4.4, so besides 4.4 you owe one
round each on 4.0, 4.1, 4.2 and 4.3.

**By default every round runs the newest one.** In the catalog, `default_package_url` in
`prepare-acp-environment.sh` pins **every built-in tier to the 4.4.0 GA installer** (env1 intl arm,
env2/env4/env6 CTYun x86, env3 hybrid, env5 intl x86). Without overrides you are testing one platform
version six times.

To run an older platform version, override both of these:

```text
release_test_acp_package_url=<installer tar for that ACP version>
release_test_environment_template=<tier template file>
```

- Leave `release_test_acp_package_url` empty and the built-in 4.4.0 installer is used.
- **Known limitation**: `release_test_acp_package_url` does not work on the **env1** tier — it fails
  immediately, so only the built-in package can be used there.
- **The tier template files are not in this repository right now.** The ones used for the August 2026
  round (`testing/environments/env5-acp-v4.1.yaml` and friends) were proposed in MR 277, which was
  closed without being merged, so they have to be recreated or obtained from whoever ran that round.

The August 2026 round is a good reference for the scope: ACP 4.0.12, 4.1.6, 4.2.5, 4.3.2 and 4.4 (GA)
each passed 75/75.

### 7.7 Step 4 — verify, then read the results

**Thirty seconds after triggering, check what the pipeline actually received.** PaC silently replaces
any parameter that is not declared in the Repository CR with an empty string: your comment is
accepted, the parameter is dropped and the run proceeds.

```bash
kubectl -n $NS get pipelinerun <run> -o json \
  | jq -r '.spec.params[] | select(.name=="env-type" or .name=="target-proxy-url" or .name=="plugin-version" or .name=="test-image") | "\(.name)=\(.value)"'
```

An empty `target-proxy-url` on env1/env3/env5 means the round is wasted; cancel and re-send.

Each run publishes its own provenance, which is the pipeline stating what it tested:

```text
report-url            = http://<report-server>/e2e-report/tektoncd-operator/<timestamp>/allure-report/index.html
environment-name      = tektoncd-operator-env1-5bvsr
acp-version           = v4.4.0
plugin-package-urls   = https://…/tektoncd-operator.latest.ALL.<version>.tgz
test-image-reference  = …/operator-e2e:<tag>
```

**A tier counts as passed only with all three**: the PipelineRun is `Succeeded=True`, there is an
Allure report URL, and you have read the scenario counts out of that report.

> To get scenario counts you have to start capturing the `run-tests` log **while it is still
> running**. Once the task reaches a terminal state the pod is reclaimed within seconds — polling
> every 20 seconds is not fast enough.

### 7.8 Upgrade testing {#78-upgrade-testing}

`to-upgrade-test` is an upgrade smoke test. Its trigger grammar is documented in the annotations of
`.tekton/to-upgrade-test.yaml`:

```text
/upgrade-test from=release-4.0                  # baseline release -> this PR's release
/upgrade-test from=release-4.0 to=release-4.2   # published -> published
/upgrade-test to=release-4.2                    # this PR's release -> published
```

Whenever "this PR's release" is involved, the artifact must exist on nexus and must have been built
from the triggering commit. A missing or stale artifact fails hard on purpose — falling back would
silently test a build without the change under test.

### 7.9 The frontend lane

`to-release-test-ui` is the release test for the console plugin; it runs the default and integration
suites and produces one report. **It competes for the same environment slots as the backend lane** and
has repeatedly taken over or deleted environments the other lane was using. Decide up front whether
the frontend rounds are part of this release's schedule.

## 8. Security scanning (static and dynamic) {#8-security-scanning-static-and-dynamic}

**Both the static and the dynamic scans that a release ships go through the QA security tooling.**

This section defines what counts as evidence; the step-by-step procedure is
[Running the release security scans](./security-scanning.md).

- The artifacts repository's `scan-vuln` pipeline ([5.3](#53-stage-d--scan-vuln-you-must-trigger-it))
  stays useful as **our own early-warning check**, but it is not release evidence.
- The security lanes on the Thanos platform are **obsolete and no longer count**. Do not run them and
  do not submit their reports.

### 8.1 Static: artifacts and images {#81-static-artifacts-and-images}

**`VulnerabilityScan` CRD — scans a whole version directory of the artifacts repository.**

| Item | Value |
| :--- | :--- |
| Resource | `security.testing.qa.io/v1alpha1`, `kind: VulnerabilityScan` |
| Namespace | **`platform-edge-security`** (it cannot run in your own project namespace) |
| Operator | Deployment `security-controller-manager` in that namespace |
| Output | An `ImageVulnerabilityReport` plus an **xlsx report**, and optionally Jira issues |

```yaml
spec:
  target:
    type: ArtifactsRepo
    artifactsRef:
      gitUrl: https://code.alauda.io/alauda-pipelines/engineering/artifacts.git
      commit: <40 lowercase hex characters>   # exactly one of branch / tag / commit
      plugins:
        - name: tektoncd-operator             # directory name under released-artifacts/
          versions:
            - v4.15                           # the version directory name, NOT a bundle version
  dbStrategy:
    mode: Frozen                              # a release scan pins the date, it does not take Latest
    frozenDbTag: <YYYY-MM-DD>                 # with dashes; a real Trivy DB image tag
  context:
    productVersion: v4.15.0                   # must be non-empty or sync-result fails
  report:
    enabled: true                             # required for a release scan
    format: xlsx                              # the only accepted value
  strategy:
    syncJira: false                           # dry run first
  workspaceStorage: 20Gi                      # the 5Gi default is too small for 30+ images
```

Four things to know before you try:

1. **It only runs in `platform-edge-security`.** Your own namespaces enforce restricted pod security,
   which blocks the scan worker outright.
2. **Never pre-create the ServiceAccount, Role or RoleBinding.** The operator creates them itself and
   refuses to adopt objects it did not create, so a hand-made one leaves the scan stuck in
   `phase=Pending` with no PipelineRun at all. Delete them and it recovers within about 15 seconds.
3. **Test whether you may create the resource with `kubectl apply --dry-run=server`.**
   `kubectl auth can-i` answers `no` to everything under a token-proxy context and will mislead you.
4. **Ship the xlsx the platform exports.** Do not assemble one by hand.

**`image-security-scanner` — scans individual images.** This is the bundled scanner project and the
source of truth for image scan commands.

- CLI scan types: `audit` (sniffer/debug tools, cracking tools, sensitive scripts, login-capable
  non-root users, UID/GID 0 non-root users, sudoers users, unexpected shells and package managers),
  `vuln` (Trivy for OS and language packages, plus secret findings), `virus` (ClamAV), or `all`.
- Database mode: `db_scanner.py` takes `PRODUCT_NAME` and `PRODUCT_VERSION`, scans every matching
  image and upserts the findings back into the CVE tables.
- It pulls layers over the registry HTTP API, so no Docker or Podman is required.

**Image inventory — the easiest thing to under-scan.** `tektoncd-operator` is an OLM operator, so the
inventory is the operator image, the bundle image, and every related image needed to use the
component (the CSV's `relatedImages`). Cluster Plugins instead scan every image listed in the release
`values.yaml`.

Configuration scanning of Helm charts, Kubernetes manifests and OLM bundles (pod security, non-root,
privilege, secrets, RBAC) belongs to the same stage.

### 8.2 Dynamic: scan the running component

Dynamic scanning uses the Ares `security_case` suite against an ACP environment that already has the
component installed.

| Variable | What to put in it |
| :--- | :--- |
| `API_URL` | API address of the target ACP |
| `REGISTRY` | registry address |
| `REGION_NAME` / `GLOBAL_REGION_NAME` | target region name / `global` |
| `USERNAME` / `PASSWORD` | ACP account — **read them from the environment, never inline them** |
| `TESTCASES` | `security_case` |
| `RESOURCE_PREFIX` | prefix for the resources this round creates |

Jira variables and a VM key path are also required; the full list is in the skill's
`references/security-scan-workflow.md`.

The dynamic cases cover privileged containers, unsafe capabilities, plaintext credentials in
environment variables, root containers, high-risk exposed services, plaintext host-port transport,
all-interface listeners, root processes, insecure transport protocols, access permissions, sensitive
API exposure, invalid or missing API tokens, CPU and memory limits, and HostPath restrictions. Two of
them need a Swagger file mounted at `/app/test_data/security/apis-swagger.json`.

The same tooling also covers CIS (kube-bench or Kubescape), STIG, OS STIG, system and web scans, and
ZAP penetration scans.

**Beware of false green.** This suite runs under `pytest-rerunfailures`, so a scenario that fails the
first time can be re-run into a pass, leaving `failed_cases` empty and the exit code zero. **Read the
short test summary of the first run**; trusting the exit code is self-deception.

### 8.3 The evidence a release owes

- Component or product name, version, release type and the **CVE database freeze date** (agree on this
  before scanning, not afterwards).
- Component type and where the image inventory came from (release `values.yaml`, CSV
  `relatedImages`, bundle metadata or a database query).
- The scanner project commit or scanner image reference.
- The exact command lines, with secrets redacted.
- Which images, product and version, artifact repository branch, Helm values, namespaces and plugin
  list were scanned.
- JSON report paths or the database update summary.
- Severity counts per image and in total.
- Audit finding counts: login-capable users, privileged users, sudoers, sniffer/debug tools, cracking
  tools, sensitive scripts, unexpected shells or package managers.
- Virus findings and ClamAV status.
- **Dynamic Ares results and Jira creation status**, including any "failed to create Jira" errors.
- CVE database update status and affected rows when database mode was used.
- A disposition for every remaining finding: fixed, false positive, known issue, not applicable,
  approved residual risk, or release blocker.

All of it is archived in the release-test repository, see [8.5](#85-where-the-reports-are-archived).

### 8.4 Where the tooling and its documentation live

Skills (in the `alauda-ai-builders` repository):

| Path | Purpose |
| :--- | :--- |
| `builders/skills/builders-alauda-security-scan/` | **The main entry point**: bundles `scripts/image-security-scanner`, `references/security-scan-workflow.md` (the flow) and `references/security-test-content.md` (static, dynamic, CIS, STIG and manual case expectations) |
| `builders/skills/builders-vulscan-artifacts/SKILL.md` | Guide for the `VulnerabilityScan` path: create, troubleshoot, re-run, clean up. Read `references/strategy-fields.md` before enabling Jira |
| `devops/skills/devops-tektoncd-vuln-fix-gitlab/` and `-github/` | Fixing what the scans find, on either lane |
| `devops/skills/devops-fix-go-vulns/` | Fixing Go dependency CVEs |

In the artifacts repository under `docs/`: `how_to_run_vuln_scan.md` (triggering,
`extra_settings.yaml` and `vuln_reviewed.yaml`, **the Jira filing convention**, remediation
principles), `scan_artifact.md`, `scan_vuln_pipeline_design.md`.

> **The skill documentation and the live environment disagree in places** (seven discrepancies have
> been recorded, including the operator's actual deployment name and namespace). Run the read-only
> checks in [8.1](#81-static-artifacts-and-images) before you follow any of it literally.

## 8.5 Where the reports are archived {#85-where-the-reports-are-archived}

**Regression reports and security reports both end up in the release-test repository**, which is the
long-term home for what a release was tested against:

`https://code.alauda.io/alauda-pipelines/engineering/release-test`

Layout, using what v4.14.0 actually looks like:

```text
plugins/tektoncd-operator/<vX.Y>/Test_Reports/
  <vX.Y.Z>/regression/          release-test rounds, one archive per round
  <vX.Y.Z>/security/            security scan results
  Non_Functional/               High_Availability / Performance / Stability
```

Inside `regression/` each round is one archive whose name carries the platform version and the tier,
alongside a `README.md` and `README_EN.md` describing the round:

```text
api-e2e-v4.0.12-env6.tgz
api-e2e-v4.1.6-env5.tgz
api-e2e-v4.2.5-env4.tgz
api-e2e-v4.3.2-env5.tgz
api-e2e-v4.4.0-rc.1549.ga57c71a7-env1.tgz   (…-env2, -env3, -env4, -env5)
api-e2e-v4.4.0-rc.1641.ga7af6d21-env2.tgz   (…-env6)
ui-e2e-v4.14.0-rc.284.g7e9f9c9-env1.tgz
```

That file list is also the clearest statement of what "coverage" means in practice: several ACP
minors, every tier, plus the frontend lane.

`security/` holds both halves of [section 8](#8-security-scanning-static-and-dynamic) — the dynamic
run's archive and the static scan's exported spreadsheet:

```text
security-runtime-ares-<id>.tar.gz
<vulnerability scan report>.xlsx
```

**Archive as you go, not at the end.** Report URLs point at a report server whose retention you do not
control, and the pods that produced them are reclaimed within minutes.

## 9. Stage I: repackage under the final version number

Once every environment has passed, there is one more step: **repackage everything under the final
`vMAJOR.MINOR.PATCH` version**. Up to this point everything has carried a build version like
`vX.Y.Z-rc.N.g<sha>`; what customers receive should be a clean `v4.15.0`.

Following what was actually done for v4.14.0:

1. **Tag the commit that passed the regression.** Not simply the newest commit — the `v4.14.0` tag
   points at the commit that `v4.14.0-rc.284.g7e9f9c9` was built from.
2. **Wait for the clean build.** Pushing the tag drives the same build chain and produces a bundle
   tagged `v4.15.0` with **its own digest**; it is not the same image as the release candidate.
3. **Update the ledger — every channel at once.** The v4.14.0 change was three lines:

   ```diff
   -latest: v4.14.0-rc.284.g7e9f9c9
   -stable: v4.14.0-rc.284.g7e9f9c9
   -pipelines-4.14: v4.14.0-rc.284.g7e9f9c9
   +latest: v4.14.0
   +stable: v4.14.0
   +pipelines-4.14: v4.14.0
   ```

   > The 4.15 line currently has only a `latest` channel, whereas 4.0, 4.6, 4.10 and 4.14 all have
   > `latest`, `stable` and `pipelines-<X.Y>`. Adding the other two at GA is very likely required —
   > **confirm with the release owner**; this note is based on what other lines look like, not on a
   > written rule.

4. **Run `/package` again**, exactly as in [stage E](#6-stage-e-build-the-offline-packages), producing
   `tektoncd-operator.latest.<arch>.v4.15.0.tgz`.
5. **Check the final packages too**: the file name, version and digest must line up with the tag.
   Never ship a release candidate as the final deliverable.

## 10. Stages J, K and L: publish the release {#10-stages-j-k-and-l-publish-the-release}

Stage I ends with the final `.tgz` files in S3. A package sitting in S3 is not yet something an IDP
environment or a customer can install — three more stages put it where it can be consumed. They are
strictly ordered, and the link between the last two is concrete: **stage L needs the pull request
number that stage K produces.**

### 10.1 Stage J — sync the packages to the mirrors {#101-stage-j-sync-the-packages-to-the-mirrors}

Packages are distributed through mirrors, and a sync service copies a package into them. It is an
HTTP API with a submit-and-poll shape. The contract below is the one the catalog's
`images/acp-release-tools/scripts/sync-package.sh` speaks, in the
[catalog repository](https://code.alauda.io/platform-edge/pipelines/catalog-incubator); the base
URL for a release is `https://package-minio-ctyun.alauda.cn:9002`.

1. **Submit one package URL.**

   ```bash
   curl --fail-with-body --silent --show-error --get "$SYNC_API_URL/sync" \
     --data-urlencode "url=<package URL>"
   ```

   The response carries a `task_id`. One call takes one URL, so a three-architecture release is
   three submissions.

2. **Poll until the task finishes.**

   ```bash
   curl --fail-with-body --silent --show-error --get "$SYNC_API_URL/status" \
     --data-urlencode "task_id=<task_id>"
   ```

   `status` ends at `done` or `error`; an error carries a message. A finished task also reports the
   object `key` it wrote, the `action` it took and the size. The script polls every 30 seconds
   against a ten-hour ceiling — treat this as a long operation, not a ten-second one.

3. **Check the key, not just the status.** The script fails the run when a finished task's key is
   not in the bucket it expected. `done` into the wrong bucket is not a successful sync.

**Then confirm by looking.** Browse `http://package-minio.alauda.cn:9002/?prefix=tektoncd-operator`
and find the new version. Until the object is visible there, stage K has nothing to point at.

> **Not verified: who runs this for a GA release.** The contract above is read from the catalog
> script, which calls it as part of the release-test flow. Whether the GA sync is driven by hand
> with these two calls or by a pipeline that wraps them is not written down anywhere this guide can
> cite. Ask the DevOps team, and record the answer here.

### 10.2 Stage K — register the version in `devops-artifact` {#102-stage-k-register-the-version-in-devops-artifact}

Alauda Cloud is fed from a **separate, GitHub-hosted artifact repository**:
`https://github.com/AlaudaDevops/devops-artifact`. Open a pull request there adding this release
under `released-artifacts/tektoncd-operator/<minor>/`.

Two shapes, both real:

| | New minor line | New patch on an existing line |
| :--- | :--- | :--- |
| Example | [PR 560](https://github.com/AlaudaDevops/devops-artifact/pull/560), `add tektoncd-operator v4.14` | [PR 564](https://github.com/AlaudaDevops/devops-artifact/pull/564), `upgrade v4.10 to v4.10.2` |
| Change | the whole directory is **added**: `acp.yaml`, `artifacts.yaml`, `extra_settings.yaml`, `metadata.yaml`, `test.yaml`, `versions.yaml`, `vuln_reviewed.yaml` | four files are **modified**: `artifacts.yaml`, `extra_settings.yaml`, `metadata.yaml`, `versions.yaml` |

What the small files hold, so you can tell whether yours are right:

- **`versions.yaml`** — the same channel-to-version mapping as the GitLab ledger; for v4.14 it is
  `latest`, `stable` and `pipelines-4.14`, all at `v4.14.0`.
- **`acp.yaml`** — `supportPlatform`, the list of ACP minors this release may be installed on. This
  is the set stage L uploads against, so it has to agree with what release testing actually covered.
- **`extra_settings.yaml`** — `release_date`, which the vulnerability tooling counts back from.
- **`test.yaml`** — the test artifacts (the operator e2e image and the frontend test image) with
  their versions and source branches.
- **`vuln_reviewed.yaml`** — registered vulnerability exemptions; empty when there are none.

**Keep the PR number.** Stage L takes it as `pull/<number>/head`, which is how the upload runs
against this change — and why stage L can start before the PR is merged.

### 10.3 Stage L — publish to Alauda Cloud with `upload-ac` {#103-stage-l-publish-to-alauda-cloud-with-upload-ac}

The last stage runs the `upload-ac` pipeline, in project `devops`, namespace `devops` on the
`integration-test` cluster:
`https://edge.alauda.cn/console-pipeline-v2/workspace/devops~integration-test~devops/pipeline/pipelines/detail/ns/upload-ac`.
Start a run from the console form and fill in:

| Parameter | Value | What it means |
| :--- | :--- | :--- |
| `revision` | `pull/<stage K PR number>/head` | the `devops-artifact` ref to upload from — this is where the PR number is used |
| `acp-version` | e.g. `v4.3`, comma-separated for several | the ACP versions to publish against |
| `upload-artifacts` | `tektoncd-operator` | which component to upload; empty means all, and the default `none` uploads nothing |
| `artifact-folder` | `released-artifacts` | the directory the plugin is looked up in |
| `ac-env` | `cn`, `io`, or `all` | domestic Alauda Cloud, overseas, or both |
| `reuse-version-meta` | `false` | reuse the metadata of the most recent application |
| `upload_versions` | e.g. `v4.10.0` | the component version to upload; empty uploads every version |

`upload-artifacts` and `upload_versions` are the two that silently do nothing when wrong:
`upload-artifacts` defaults to `none`, and an empty `upload_versions` means *every* version rather
than the one you have in mind.

**A green pipeline is not a published release.** The run uploads the artifact; the version then has
to be **reviewed and listed on Alauda Cloud itself**, by a person. Until that review passes and the
version is listed, nothing has been published — so a release is not finished when stage L goes
green, it is finished when the listing is live.

> **Not verified: the review and listing procedure itself** — who reviews, where in the Alauda Cloud
> console it is done, and what it looks like when it is approved. Ask whoever owns the listing, and
> write it in here.

### 10.4 Review and closeout

Stages J-L publish the artifact, but they do not replace the release review or post-publication
closeout. Use [Release Review and Closeout](./release-review-and-closeout.md) to:

- close the non-functional gate before Stage I;
- collect the release review evidence;
- release the Jira version and update the download template;
- complete the operator release record and Bugfix/Security Errata;
- verify domestic and overseas Cloud listings;
- generate, approve and archive the release email.

## 11. Release-test environments: where the time goes

This is the part of the chain that most easily burns a night.

### 11.1 Three ways to get an environment, 45x apart in cost

| How | When it happens | Cost |
| :--- | :--- | :--- |
| **Reuse handle short-circuit** | The `existing-environment` secret has an address plus credentials | **under 2 minutes** |
| **Adopt a Ready environment** | No handle, but the platform has a Ready environment for that tier that is **less than 8 hours old** | seconds to a minute |
| **Rebuild** | Neither of the above | **about 1.5 hours**, and it has to queue for quota |

There is a fourth way, outside this lane: **build the environment yourself on IDP first**. That is how
the manual env5 tier gets an environment at all, and it is also the way to separate "the environment
cannot be built" from "the test cannot run". How to create it, how to watch it come up, and how to
hand it to this lane are in
[Build a Release-Test Environment by Hand](./release-test-environment.md).

### 11.2 Check two numbers before you trigger

**Is the reuse handle still there?** One secret per tier:

```bash
kubectl -n $NS get secret \
  tektoncd-operator-release-existing-environment-env2 -o json | jq -r '.data | keys | @csv'
```

Eight keys (`address`, `token`, `username`, `password`, `kubeconfig`, `management-kubeconfig`,
`env-type`, `environment-name`) means the short-circuit can fire. **Only `env-type` means the handle
was deliberately emptied** to force a real rebuild, and you will go down the adoption path instead.

**How long until the environment falls out of the adoption window?** Adoption has an 8-hour limit
measured from when the environment was created (`stale_threshold_seconds=28800`). The
`prepare-environment` log prints its reasoning:

```text
probing the Ready environment before adoption: environment=… created_at=… age_seconds=22161 stale_threshold_seconds=28800
environment preparation completed: mode=adopted environment=… probes=1
```

> A measured example: at trigger time four environments were at `age_seconds` 22161, 22231 and 22670
> against a threshold of 28800 — **about 1 hour 42 minutes of margin left**. Triggering an hour later
> would have meant tearing all of them down and rebuilding, at roughly 1.5 hours each plus quota
> queueing. **So the first thing to do on this lane is to check these two numbers, not to post the
> comment.**

### 11.3 Two more clocks

- **Reclamation.** After a test finishes, the environment starts a countdown
  (`recycle.when=Completed` with `delay_seconds=28800`) and is then destroyed. A suite takes one to
  two hours, so before triggering, check that "now plus two hours" does not cross the scheduled
  reclamation time.
- **Quota.** The CTYun personal quota is around 288 vCPU, which means **at most three five-node
  environments at a time**. A fourth sits in `WaitingForSubResourceReady` and eventually reports an
  infrastructure timeout whose real cause is `Relay.Quota.Exceeded`. Adopting an existing environment
  creates no machines and does not count against this.

## 12. Acceptance criteria at a glance

| Stage | The only evidence that counts | What is not evidence |
| :--- | :--- | :--- |
| A | The `chore/update-components-*` MR exists | "the pipeline went green" |
| B | A new version tag exists | overall success (only `image-scan` red is fine) |
| C | The `mergerequest-url` result plus `changed=1` | a green run (it is green even when `operatorBranch` was forgotten) |
| D | The bot's `[ci skip]` commit is the MR head, and the scan report has been posted | "there is a green check on the MR" |
| E | The three log lines for your version: packaged, uploading, checksum | the pipeline's final state, see [6.1](#61-every-package-built-and-uploaded-pipeline-still-red) |
| F | `lint-docs` and `check-translations` both green | `auto-translate-*`, which is allowed to fail |
| G | `Succeeded=True` plus an Allure report plus scenario counts, **and the coverage is complete** (six tiers, every supported ACP minor), archived per [8.5](#85-where-the-reports-are-archived) | a green pipeline with no report; or declaring victory after the four automated tiers |
| H | Static (platform-exported xlsx with a complete image inventory) and dynamic (Ares first-run summary) results, with the evidence checklist filled in and both archived per [8.5](#85-where-the-reports-are-archived) | `scan-vuln` MR comments; obsolete Thanos reports; a hand-assembled xlsx; an Ares exit code |
| N | High Availability, Performance and Stability are each newly archived, explicitly reused with owner approval, or confirmed not applicable | "Reference the previous release" without an owner decision |
| I | Every channel in the ledger points at `vX.Y.Z` and `…vX.Y.Z.tgz` exists | shipping a release candidate |
| J | Every GA architecture has a completed sync task and the expected mirror object is visible | A `done` task with the wrong key, bucket or size |
| K | The Cloud registration PR contains the correct version directory and its number is retained for L | Treating the GitLab artifacts MR as the Cloud registration PR |
| L | `upload-ac` succeeds, both environments are manually approved, and both listings are visible | The `upload-ac` PipelineRun alone |

## 13. The traps, roughly in order of how often people hit them

1. **Forgetting the SOCKS proxy on env1/env3/env5** — every package is re-uploaded, costing tens of
   minutes.
2. **Using a floating tag as the test image** — the environment silently runs the old image.
3. **A parameter that was accepted but dropped** — PaC blanks anything not declared in the Repository
   CR. **Verify the run's actual parameters within 30 seconds.**
4. **Packaging too early** — before the head moved to the bot's `[ci skip]` commit you are packaging
   the old `artifacts.yaml`.
5. **Assuming `scan-vuln` ran by itself** — `[ci skip]` makes PaC skip that head entirely.
6. **Reading "pipeline red" as "this step failed"** — see [2.4](#24-the-pipeline-is-red-does-not-mean-this-step-failed).
7. **Forgetting `operatorBranch`** — only the main line is synchronised while the run stays green.
8. **Triggering after the 8-hour adoption window closed** — all environments get rebuilt.
9. **Trying to fetch `run-tests` logs afterwards** — the pod is gone within seconds; capture while it
   runs.
10. **Cancelling with `Cancelled`** — finally never runs, environments and vclusters are never
    released, and the next round fails on "already in use".
11. **Stopping after the four automated tiers** — env5 (manual) and env6 are also required, and every
    supported ACP minor needs its own round.
12. **Comparing the package version with the test image version** — they are not supposed to match.
13. **Shipping a release candidate as the deliverable** — stage I exists for a reason.
14. **Submitting the wrong scan as security evidence** — releases use the QA security tooling;
    `scan-vuln` is our own check and the Thanos lanes are obsolete.
15. **Creating `VulnerabilityScan` in your own namespace, or pre-creating its RBAC** — the first is
    blocked by pod security, the second leaves the scan pending forever.
16. **Scanning only the operator image for an OLM component** — the bundle image and every
    `relatedImages` entry belong to the inventory.
17. **Trusting the Ares exit code** — read the first run's summary.
18. **Starting Stage I with an unresolved non-functional gate** — N is an engineering gate, not a
    review-page decoration.
19. **Calling a release complete when `upload-ac` is green** — domestic and overseas review and
    listing confirmation are still required.
20. **Treating a vulnerability registration as risk acceptance** — an owner or security approver
    must explicitly accept residual risk before the security gate can close.

## 14. Appendix A: one real end-to-end round (v4.15.0, September 2026)

| Item | Value |
| :--- | :--- |
| Bundle | `v4.15.0-rc.302.gdbf0be2`, digest `sha256:d97f5dbfa0a2048af40ca1bd8b3cd6c41f23a2395d62b286b77804120ec69ef5` |
| Packages | `tektoncd-operator.latest.{amd64,arm64,ALL}.v4.15.0-rc.302.gdbf0be2.tgz` |
| Test image | `operator-e2e:v4.15.0-rc.307.ge6ea9cf` |
| ACP version | `v4.4.0` |

Release testing, all `Succeeded=True` with `Tasks Completed: 11 (Failed: 0)`:

| Tier | Run | Duration |
| :--- | :--- | :--- |
| env1 | `to-release-test-nfwnm` | 1h01m07s |
| env3 | `to-release-test-c2sfk` | 1h10m26s |
| env4 | `to-release-test-rqgm8` | 1h16m05s |
| env2 | `to-release-test-8mhzd` | 1h20m27s |

The three skipped tasks (`sync-test-dependency`, `deploy-test-dependency`,
`deploy-test-prerequisite`) are skipped by design: they exist for plugins that depend on
tektoncd-operator, and here the operator is the subject itself.

> This round covered **the newest ACP only, on the four automated tiers**. It did not run env5 or
> env6, did not cover ACP 4.0 to 4.3, did not include the security scans, did not repackage under
> the final version number, and stopped well before publication. By the standards in sections 7.6,
> 8, 9 and 10 it is **not a complete release** — it is here as an example of what one healthy round
> looks like.

## 15. Appendix B: command reference

These assume you have already selected the build cluster context.

```bash
export NS=alauda-pipelines-build

# Overall state of a run
kubectl -n $NS get pipelinerun <run> \
  -o jsonpath='{.status.conditions[0].status}{" "}{.status.conditions[0].reason}{" "}{.status.conditions[0].message}{"\n"}'

# Per-task state (find out which step is red)
kubectl -n $NS get taskrun -l tekton.dev/pipelineRun=<run> \
  -o custom-columns='TASK:.metadata.labels.tekton\.dev/pipelineTask,STATUS:.status.conditions[0].reason'

# Provenance and report URLs the pipeline publishes
kubectl -n $NS get pipelinerun <run> \
  -o jsonpath='{range .status.results[*]}{.name}={.value}{"\n"}{end}'

# The 30-second check: what the pipeline actually received
kubectl -n $NS get pipelinerun <run> -o json \
  | jq -r '.spec.params[] | "\(.name)=\(.value)"'

# Logs of one step, while the pod still exists
kubectl -n $NS logs <taskrun>-pod --all-containers --tail=200

# Cancel (always CancelledRunFinally)
kubectl -n $NS patch pipelinerun <run> \
  --type=merge -p '{"spec":{"status":"CancelledRunFinally"}}'
```

## 16. Keeping this guide honest

This guide describes pipelines that live in this repository. **When you change a lane under
`.tekton/` or the parameters it accepts, update this page in the same merge request.** A process
document in a different repository — or in a wiki — drifts out of date within a release or two, and
the next person pays for it.

Three things it describes are **not** in this repository and will drift silently: the shared catalog
pipelines, the sync API contract in [10.1](#101-stage-j-sync-the-packages-to-the-mirrors), and the
`upload-ac` parameters in [10.3](#103-stage-l-publish-to-alauda-cloud-with-upload-ac). When you run a
release and any of them has moved, correct it here in the same week — and fill in the two items
marked "not verified" in section 10 as soon as someone can tell you the answer.

The release review and closeout page also depends on external Jira, Cloud, Errata and mail systems.
Keep those actions as evidence-backed post-publication steps; do not replace them with a statement
that the final package was uploaded.
