---
weight: 20
---

# Running the env5 regression by hand

env5 is the one tier the automated `to-release-test` batch never covers: someone has to drive it.
This guide is that procedure — **from a working environment to an archived report**.

It deliberately starts *after* the environment exists. Provisioning an environment (requesting it,
choosing its shape, waiting for it to come up) is a separate topic and is not repeated here.

For the rest of the release — what the six tiers are, which ACP versions must be covered, what the
automated lane does — see [the release process guide](./index.md).

## 1. What the environment must give you {#1-what-the-environment-must-give-you}

Confirm all five before you start. Every one of them has bitten a real round.

| Requirement | How to check | If it is missing |
| :--- | :--- | :--- |
| The platform answers | `curl -sk <platform>/dex/pubkey` returns 200 | The console returning 502 does **not** mean the platform is down — the API layer and the console UI are separate. Check this path, not `/`. |
| A cluster to test on | `kubectl get clusters` lists it as `Running` | Two-cluster environments exist: the plugin belongs on the **business** cluster, not on `global`. |
| A default StorageClass on that cluster | `kubectl get sc` | Install one — see [section 3](#3-make-sure-there-is-a-default-storageclass). Several scenarios claim a volume and will fail without it. |
| Nodes can pull from the platform registry | after installing anything, `kubectl get pods -o jsonpath=…image` | See [the image-rewrite trap](#trap-images-rewritten-to-an-unreachable-registry). |
| A host that can reach both the package mirror and the platform | `curl` from it to each | Packages are gigabytes; pushing them from a laptop over a VPN fails halfway. Use a host on the same network. |

The platform address, the admin account and the cluster names all come from the environment's own
record; read them from there rather than from notes.

## 2. Get a kubeconfig for every cluster {#2-get-a-kubeconfig-for-every-cluster}

The platform's dex only supports `authorization_code`, so there is no password grant to curl. Use
the `get_kubeconfig.py` helper that ships inside the `test-plumbing` images, once per cluster:

```bash
python scripts/get_kubeconfig.py \
  --url https://<platform> --username admin --password "$(cat <password-file>)" \
  --cluster <cluster-name> --output kubeconfig-<cluster-name>.yaml
```

- **Never pass the password on the command line** — it lands in the process list. Read it from a
  file with `0600` permissions, and delete that file when the round is over.
- **Verify the two files differ.** A helper that silently falls back to `global` produces two files
  of identical size; compare their `server:` entries before trusting them.
- Each file carries two contexts: `proxy-connect` (through the platform gateway) and
  `direct-connect` (straight to the API server). On an IPv6-only environment the direct address is
  an IPv6 literal, which a jump host usually cannot route — **use the proxy context**.

The token inside is long-lived. It must never be written into a document, a log or a chat message.

## 3. Make sure there is a default StorageClass {#3-make-sure-there-is-a-default-storageclass}

```bash
kubectl get sc
```

If it prints `No resources found`, install `topolvm-operator` on the business cluster and create a
default StorageClass from it. Three things go wrong every time:

1. **The CSI sidecar images may not exist anywhere on the platform.** The operator points at
   `public.registry/3rdparty/k8scsi/*`, a hostname that does not resolve. On a full platform the
   images are already in the registry under different tags and you only fix the addresses; on a
   minimal platform they are absent and must be mirrored in first. List the registry catalog with
   admin credentials before concluding either way — an unauthenticated query returns an empty tag
   list that looks exactly like "not there".
2. **Patching the operator Deployment does not stick** — OLM reverts it. Patch the CSV so that the
   operator reads the settings ConfigMap, and change that ConfigMap only *after* the operator has
   generated it; a ConfigMap created beforehand is overwritten wholesale.
3. **Device names need the `/dev/` prefix.** The per-node ConfigMap lists bare names such as `vdb`;
   copying that into the cluster CR produces a "disk is dirty" error whose text has nothing to do
   with the real cause.

Then create the StorageClass yourself — the operator does not:

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: sc-topolvm
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: topolvm.cybozu.com
parameters:
  csi.storage.k8s.io/fstype: xfs
  topolvm.cybozu.com/device-class: hdd
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
```

**Acceptance is not "the CR went green".** Claim three volumes at once and check that you get three
*different* volume IDs:

```bash
kubectl get logicalvolumes.topolvm.cybozu.com \
  -o custom-columns='NAME:.metadata.name,NODE:.spec.nodeName,VOLID:.status.volumeID'
```

## 4. Install the plugin build under test {#4-install-the-plugin-build-under-test}

Upload the package twice. The first push uploads the images and registers the package on `global`,
where the catalog lives; the second only registers it for the business cluster and takes seconds.

```bash
violet push <plugin>.tgz --platform-address https://<platform> \
  --platform-username admin --platform-password "$PW"
violet push <plugin>.tgz --platform-address https://<platform> \
  --platform-username admin --platform-password "$PW" \
  --clusters <business-cluster> --skip-push
```

Verify the download before pushing: the file size must equal the source's `Content-Length`, and
`tar tzf` must list the archive. Then check the cluster side, because a successful push does not
prove the package is installable:

```bash
kubectl -n cpaas-system get artifactversion | grep <plugin>      # Present / Success
kubectl -n cpaas-system get packagemanifest <plugin> \
  -o jsonpath='{range .status.channels[*]}{.name}{" -> "}{.currentCSV}{"\n"}{end}'
```

`packagemanifest` lags `artifactversion` by a few minutes — wait for the channel to appear rather
than concluding the push failed.

Install through OLM on the business cluster, with `installPlanApproval: Manual` (the platform's
webhook rejects `Automatic` for in-house operators) and the suggested namespace from the
package manifest. Approve the InstallPlan, then wait for the CSV and for `TektonConfig`:

```bash
kubectl -n <ns> patch installplan <name> --type=merge -p '{"spec":{"approved":true}}'
kubectl -n <ns> get csv           # PHASE=Succeeded
kubectl get tektonconfig          # READY=True
```

### Trap: images rewritten to an unreachable registry {#trap-images-rewritten-to-an-unreachable-registry}

On some environments the marketplace rewrites images that have no whitelist rule to
`<platform-host>/3rdparty/...`, and the nodes cannot pull from that host. The trap is that it only
breaks *half* the images — the plugin's own images have rules and pull fine — so the environment
looks healthy while the test images fail later.

Do not predict this from the shape of the platform address. Measure it, right after installing:

```bash
kubectl -n <ns> get pods -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.image}{"\n"}{end}{end}' | sort -u
kubectl -n <ns> get pods -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.image}{"\n"}{end}{end}' | grep -c 3rdparty
```

Every image should come from the platform registry and the count should be `0`.

## 5. Get the e2e package into the environment {#5-get-the-e2e-package-into-the-environment}

The suite runs from a test image, and an air-gapped environment cannot pull that image from the
build registry. It has to arrive as a package.

**Check the release line has one.** If the mirror returns 404 for
`tektoncd-operator-e2e/<line>/…`, the package does not exist yet and you have to create it: record
the image set and trigger `artifacts-package-e2e`, as in
[6.3 of the release process guide](./index.md#63-the-second-package-tektoncd-operator-e2e). Two
things save time there:

- **Do not rebuild the test image reflexively.** If `git diff --name-only <image-commit>..<HEAD> -- testing/`
  is empty, the existing image is functionally identical *and* is the one the automated tiers are
  using, which makes the results comparable. Rebuild only when `testing/` actually changed.
- **Confirm provenance from the image, not the tag.** `crane config <ref>` prints
  `org.opencontainers.image.revision` and `ref.name`; a tag can say anything.

**Push it like any other package** (both clusters, as in [section 4](#4-install-the-plugin-build-under-test)).

`violet push` on this package **exits non-zero** with `failed to sync modulePlugin: Object 'Kind' is
missing in 'null'`. That is expected: the e2e package is image-only — it has no `moduleplugin.yaml`
— and the failure happens in the last step, after every image has been uploaded. Confirm the images
landed rather than treating the exit code as fatal:

```bash
skopeo list-tags --creds "admin:$RP" docker://<platform>/<repo>
skopeo inspect --creds "admin:$RP" --raw docker://<platform>/<repo>:<tag> | sha256sum
```

The index digest must equal the source registry's. If it does, the environment is testing exactly
what the automated tiers are testing.

## 6. Run the suite {#6-run-the-suite}

Run it as a Job on the business cluster. The image's entrypoint is the bare test binary, so the
wrapper has to be invoked explicitly:

```yaml
command: ["/home/nonroot/testing/lynx-entrypoint.sh"]
env:
  - name: API_URL                    # the suite reaches the cluster through the platform gateway
    value: https://<platform>
  - name: REGION_NAME
    value: <business-cluster>
  - name: USERNAME                   # from a Secret, never inline
  - name: PASSWORD
  - name: LYNX_TAGS
    value: "@e2e"
  - name: LYNX_INSTALL_OPERATOR
    value: "false"
  - name: LYNX_OPERATOR_NAMESPACE
    value: <namespace the operator was installed into>
  - name: LYNX_STORAGE_CLASS_NAME
    value: sc-topolvm
  - name: LYNX_WITH_TOOLCHAIN
    value: "true"
  - name: LYNX_FAIL_ON_TEST_FAILURE
    value: "false"
  - name: TEST_RESULT_DIR
    value: /results                  # mount a PVC here
```

Mount a PVC at `TEST_RESULT_DIR`; the report is written there and the Job's own filesystem goes away
with it.

### The two settings that decide whether you tested anything {#the-two-settings-that-decide-whether-you-tested-anything}

Both of these produce a **passing run that covered almost nothing**, which is the hardest kind of
failure to notice.

- **`LYNX_TAGS` must be set to `@e2e`.** With nothing set, the wrapper falls back to `@dailybuild`,
  the daily-build smoke subset, while the suite's own Makefile defaults to `@e2e`. The two defaults
  disagree. Measured on one release line: `@e2e` appears 37 times across the feature files,
  `@dailybuild` 11.
- **Leave `LYNX_MAKE_TARGET` alone.** The default target runs both buckets; running only the
  parallel one appends `~@serial` and silently drops every scenario that must not run concurrently
  — 22 of them — while still reporting a pass.

The wrapper's own source says it plainly: *selecting zero scenarios reports as a pass and would hide
the misconfiguration.*

So before you look at the score, look at what was selected:

```bash
kubectl -n <ns> logs job/<job> | grep "running the suite"
# ===> phase: running the suite: make test TAGS='@e2e'
```

### What else to expect {#what-else-to-expect}

- `LYNX_OPERATOR_NAMESPACE` must name the namespace you actually installed into. The wrapper skips
  installation when it finds a healthy CSV, but it only looks in that one namespace; get it wrong
  and it tries to create a second Subscription, which the platform webhook rejects and the Job dies
  in seconds.
- The self-hosted toolchain takes six or seven minutes to come up the first time (`GitLab pod
  phase=Running ready=false` repeats throughout — that is normal). A second run on the same
  environment reuses it and starts in about a minute.
- Report generation retries an analytics endpoint it cannot reach and fails; this does not affect
  the output.

## 7. Read the result {#7-read-the-result}

The authoritative number is in the report, not in the Job's exit code:

```bash
cat <results>/allure-report/widgets/summary.json
# {"statistic":{"failed":0,"broken":0,"skipped":0,"passed":76,"unknown":0,"total":76}}
```

**Cross-check it against the raw results**, and expect a discrepancy if you ran the suite more than
once on the same volume:

```bash
ls <results>/allure-result/*-result.json | wc -l
```

The suite's `clean` step removes its own working directory but **not** the result directory the lane
writes to, so a second run leaves the first run's raw results in place. Split them by modification
time before concluding anything — the report counts the current run, the directory holds both.

## 8. Archive the report {#8-archive-the-report}

Reports live in the release-test repository under
`plugins/tektoncd-operator/<line>/Test_Reports/<version>/regression/`.

Match the conventions already in that directory:

- **The version in the file name is the ACP version, not the plugin version**:
  `api-e2e-<acp-version>-env5.tgz`.
- **The archive has one top-level directory named after itself**, containing `allure-report/`.
- **Include `allure-report/widgets/environment.json`.** A manual run has no PipelineRun to record
  it, so write one by hand: plugin version, ACP version, test image and its index digest, the tag
  selector, and the Job name. The previous release's env5 archive shipped without it, and that
  directory's README records that its run details could not be read back as a result.
- Update both `README.md` and `README_EN.md` with a row for the new archive, and state the scope —
  which tags were excluded, and therefore what the report does **not** cover.

Open a merge request. Do not merge it yourself.

## 9. Traps, in one place {#9-traps-in-one-place}

| Symptom | Real cause |
| :--- | :--- |
| Suite passes in minutes with a small number of scenarios | `LYNX_TAGS` unset — ran the `@dailybuild` smoke subset |
| Suite passes but serial scenarios never appear | Ran `test-parallel` instead of the default target |
| Job dies in seconds on a Subscription webhook error | `LYNX_OPERATOR_NAMESPACE` does not match where the operator is installed |
| Scenarios that need a volume fail | No default StorageClass, or it is not authorized for the project |
| `violet push` exits non-zero on the e2e package | Image-only package has no `moduleplugin.yaml`; check the images and the digest instead |
| Test images fail to pull while the plugin's own images work | Marketplace rewrote them to a registry the nodes cannot reach |
| `topolvm-controller` crash-loops on `csidrivers … not found` | The cluster CR has not been created yet — this is a missing step, not a broken image |
| Report and raw results disagree on the count | A previous run's results are still in the same directory |
| Console returns 502 | The console is a separate component; the platform API may be perfectly healthy |

## 10. One completed round, for reference {#10-one-completed-round-for-reference}

| | |
| :--- | :--- |
| Plugin | `v4.15.0-rc.312.g96d7964` |
| Test image | `operator-e2e:v4.15.0-rc.307.ge6ea9cf`, index `sha256:3ae02ffa3f94ca2d54492577ccb001116c91cba2d1a3a8d3ad129ce829fa833a` |
| Platform | ACP v4.4.0, IPv6 single stack, `global` + business cluster, 4 nodes |
| Storage | topolvm, `sc-topolvm` default |
| Selector | `@e2e` |
| Result | **76/76**, nothing failed, broken or skipped |
| Duration | 36.9 minutes |

Elapsed from "environment exists" to "report archived" was roughly three hours, most of it spent
creating the e2e package for a release line that did not have one yet and transferring it. On a line
whose package already exists, the same round is well under an hour.
