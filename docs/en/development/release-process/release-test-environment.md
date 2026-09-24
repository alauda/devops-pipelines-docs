---
created: '2026-09-17'
updated: '2026-09-17'
weight: 40
---

# Build a Release-Test Environment by Hand

The release-test lane normally provisions its own ACP environment: you post a `/test to-release-test`
comment and the catalog's `prepare-acp-environment` Task either reuses a recorded environment, adopts
a Ready one, or builds a new one from a built-in tier template. That path, and what each option
costs, is section 11 of the [Release Process](./index.md) guide.

This page covers the other case — you build the environment **yourself, on IDP, before the lane
runs**. You need it when:

- **env5 is not part of the automated batch.** Someone has to stand that tier up and trigger it by
  hand; it is still mandatory for a release (Release Process, section 7.6).
- You need a shape the built-in template does not give you — an older ACP, a different installer
  flavour, an extra node.
- The lane's own provisioning keeps failing and you want to separate "the environment cannot be
  built" from "the test cannot run".

Everything below was measured on one real environment, built on 2026-09-17: `CustomAcp`
`devops-4k2mf` in namespace `idp`, display name `devops-tekton-4.15`. Credentials (the IDP
kubeconfig, platform accounts) are deliberately not in this page — ask the DevOps team for them.

## 1. What an env5-shaped environment is

env5 is the only tier that is **two clusters**, x86, and IPv6-only. The authoritative shape is the
tier template kept next to the catalog Task:
`task/prepare-acp-environment/0.1/environments/env5.yaml` in
`https://code.alauda.io/platform-edge/pipelines/catalog-incubator`.

The table below only mirrors that file — it was read at commit
`200bee6c364bc731177fded1724cd36acd4d6a23`. **If the two ever disagree, the file wins**: correct the
table, and correct the environment you built, not the other way round.

| | `global` region | `devops` region |
| :--- | :--- | :--- |
| Role | Platform control plane | Where the release test actually runs |
| Nodes | 1 master | 3 masters + 1 worker |
| CPU / memory | 16C / 32G | 16C / 32G per node |
| Root disk | 300G | 100G per node |
| Data disks | none | 2 x 50G per node (this is where Ceph OSDs land) |
| OS | RHEL 8.10 | RHEL 9.6, with one master and the worker on 8.10 |
| CNI | kube-ovn | kube-ovn |
| Network mode | overlay, load balancer `HA` | **underlay**, load balancer `vip`, plus one extra VIP |
| IP family | IPv6 only | IPv6 only |

Two consequences worth knowing before you build anything:

- **`global_region_as_business` is false for this tier**, so the plugin under test is installed into
  the `devops` region, not into `global`. The catalog script defaults env5's `clusters` to `devops`
  for exactly this reason.
- **The tier template adds one L5 plugin, `rook-operator`**, staged `after-platform-deploy` onto the
  `devops` region. ACP core does not ship rook, and without it the tier has TopoLVM (RWO) and **no
  ReadWriteMany**. If your workload needs RWX, a hand-built environment needs rook installed too —
  creating the clusters is not enough.

## 2. Prerequisites

| What | How to get it |
| :--- | :--- |
| IDP web access | `https://idp.alauda.cn` — the environment list is under **Environments** |
| IDP cluster kubeconfig | From the DevOps team. Its API server is `https://idp.alauda.cn/kubernetes`; every environment CR lives in namespace `idp` |
| Team membership | The CR carries `idp.alauda.io/team` (`devops` here). Without it the environment will not show up as yours in the UI |
| A subnet | `spec.*.subnetRef` points at a `Subnet` in namespace `idp`. `default` is the one this environment used |
| Machine quota | Seven machines per env5 environment (see section 4). Quota is per provider and shared; if you are about to build a second environment, check with whoever owns the pool first — this page does not have a verified number for the IDP KVM provider |

Every command below assumes the IDP kubeconfig is selected:

```bash
export KUBECONFIG=<your idp kubeconfig>
```

## 3. Step 1 — create the environment

### 3.1 In the UI

**Environments → create → Custom ACP**. "Custom" is the right kind: the single-node kinds
(`AllInOneAcp` and friends) cannot express two regions. Fill in the shape from section 1.

The UI writes a `CustomAcp` object. Everything the UI does is visible — and repeatable — as that
object, which is why the next section exists.

### 3.2 As YAML

This is the spec of the 2026-09-17 environment, with the Crossplane runtime fields
(`resourceRef`, `providerRef`, `compositionRevisionRef`, and the two update policies) removed —
they are filled in by the controller, not by you.

```yaml
apiVersion: env.idp.alauda.io/v1alpha1
kind: CustomAcp
metadata:
  name: <your-name>
  namespace: idp
  annotations:
    cpaas.io/display-name: <display name>
  labels:
    idp.alauda.io/category: acpplatform
    user.idp.alauda.io/resource-purpose: sprint-release-testing
spec:
  packageName: installer-core-v4.4.0-x86
  products:
    - acp
  provider: alauda-idp-kvm
  compositionRef:
    name: customacp
  console:
    endpointType: domain
  registry:
    address: registry.alauda.cn:60070
    mode: internal
  machineClasses:
    - name: large
      cpu: 16
      memory: 32
      os: redhat-9.6
      rootDiskSize: 300
      networkInterface:
        name: eth0
      extraNetworkInterfaces:
        - name: eth1
      underlayNetworkInterface:
        name: underlay0
    - name: normal
      cpu: 16
      memory: 32
      os: redhat-9.6
      rootDiskSize: 100
      disks:
        - size: 50
        - size: 50
      networkInterface:
        name: eth0
      extraNetworkInterfaces:
        - name: eth1
      underlayNetworkInterface:
        name: underlay0
    - name: normal-2
      cpu: 16
      memory: 32
      os: redhat-8.10
      rootDiskSize: 100
      disks:
        - size: 50
        - size: 50
      networkInterface:
        name: eth0
      extraNetworkInterfaces:
        - name: eth1
      underlayNetworkInterface:
        name: underlay0
  global:
    arch: amd64
    ipProtocol: ipv6
    hostnameAsNodename: false
    cni:
      type: kube-ovn
      ovnArgs:
        transmitType: overlay
    controlPlane:
      count: 1
      machineClass: large
    entryAddr:
      type: loadbalancer
    subnetRef:
      name: default
      namespace: idp
    postHooks:
      - image: registry.alauda.cn:60080/idp/cluster-hook
        tag: master
        command:
          - python3
          - /app/setup_acp_license.py
  clusters:
    - name: devops
      arch: amd64
      ipProtocol: ipv6
      hostnameAsNodename: false
      cni:
        type: kube-ovn
        ovnArgs:
          transmitType: overlay
      controlPlane:
        count: 3
        machineClass: normal
      nodeGroups:
        - name: worker
          count: 1
          machineClass: normal-2
      entryAddr:
        type: loadbalancer
      subnetRef:
        name: default
        namespace: idp
```

Field notes, in the order people get them wrong:

- **`machineClasses` is where the hardware is declared**, and each region only references a class by
  name. `large` is the `global` master (300G root, no data disks); `normal` is a `devops` master;
  `normal-2` exists only to put one node on RHEL 8.10, which is how the tier gets its mixed-OS
  coverage.
- **`spec.global` is one region and `spec.clusters` is a list of the others.** A one-cluster
  environment simply has an empty `clusters`.
- **`postHooks` on `global` installs the ACP licence.** Leave it in; without it the platform comes up
  unlicensed.
- **`packageName` must be a package IDP already has registered**, not a URL. The built-in env5 tier
  uses the **international** x86 installer, which is a different package from the one in the YAML
  above — see section 7.
- **`hostnameAsNodename: false`** is why the nodes end up named after their IPv6 address
  (`v6-<address with its separators rewritten>`) rather than after a hostname. The tier template
  sets the opposite; it changes nothing functionally, but it does change what you grep for.

## 4. Step 2 — watch it come up

### 4.1 The chain

One `CustomAcp` fans out into five kinds. Knowing the chain is what turns "it is still spinning" into
"it is stuck **here**":

```text
CustomAcp            idp/<name>                      what you created; SYNCED + READY columns
  └─ XCustomAcp      <name>-<suffix>                 cluster-scoped, composition=customacp
       └─ ACPPlatform  idp/<name>-<suffix>            status.phase, endpoint, admin account
            ├─ ACPCluster  idp/<name>-<suffix>-cluster0   the devops region
            └─ Machine     idp/…                           one per node, plus one LB per region
```

The `<suffix>` is generated: `devops-4k2mf` became `devops-4k2mf-7ssd9`. Read it once and reuse it:

```bash
PLATFORM=$(kubectl -n idp get customacps.env.idp.alauda.io <name> -o jsonpath='{.status.platform.name}')
```

### 4.2 What to poll

Top level — the two columns answer "is it done":

```bash
kubectl -n idp get customacps.env.idp.alauda.io <name>
# NAME            SYNCED   READY   CONNECTION-SECRET   AGE
# devops-4k2mf    True     True                        117m
```

`SYNCED=True` means the request was accepted and reconciled; it flips within seconds and says nothing
about progress. **`READY=True` is the finish line.** The same information with timestamps, which is
what you want when you are reconstructing how long something took:

```bash
kubectl -n idp get customacps.env.idp.alauda.io <name> \
  -o jsonpath='{range .status.conditions[*]}{.type}={.status} {.reason} {.lastTransitionTime}{"\n"}{end}'
```

Platform level — this is the useful progress signal:

```bash
kubectl -n idp get acpplatforms.env.alauda.io "$PLATFORM" \
  -o jsonpath='{.status.phase}{"\n"}{.status.platformEndpoint}{"\n"}'
```

`phase` moves **`installing` → `configuring` → `ready`**. `platformEndpoint` appears while still
`configuring`, so you can test connectivity early — but do not start pushing packages then, the
marketplace and OLM are not laid down yet.

Machine level — where a build actually gets stuck, because this is the part that needs
infrastructure:

```bash
kubectl -n idp get machines.env.alauda.io | grep "$PLATFORM"
```

Every row should reach `ready`. An env5 environment has **seven**: 1 `global` master, 3 `devops`
masters, 1 `devops` worker, and 2 load balancers (one per region, on Debian). A machine that sits in
a pending phase for tens of minutes is an infrastructure problem — quota, subnet, or the provider —
not something a later retry of the test will fix.

Cluster level — once the platform is up, each region registers as a cluster:

```bash
kubectl -n idp get acpclusters.env.alauda.io | grep "$PLATFORM"
# devops-4k2mf-7ssd9-cluster0   devops-4k2mf-7ssd9   kvm   ready
```

### 4.3 A measured timeline

From the 2026-09-17 environment, all times UTC:

| Elapsed | Time | What happened |
| :--- | :--- | :--- |
| 0 | 03:45:30 | `CustomAcp` created, `Synced=True` |
| +4s | 03:45:34 | 4 machines start: the `global` master and the 3 `devops` masters |
| +3m | 03:48:34 | `global` load balancer, then the `devops` worker (the RHEL 8.10 one) |
| +5m36s | 03:51:06 | `devops` load balancer |
| +16m | 04:01:27 | `global` registered as a cluster on the platform |
| +38m | 04:23:12 | the `<platform>-service-access` Secret appears |
| +38m | 04:23:19 | `devops` registered as a cluster |
| **+53m12s** | **04:38:42** | **`Ready=True`** |

So: **about 55 minutes**, with the machines up in the first six and the remaining three quarters of
the time spent installing and configuring ACP itself. If machines are still not `ready` after ten
minutes, the problem is infrastructure and waiting will not help.

### 4.4 Two things that are not the ready signal

- **The `<platform>-service-access` Secret is not the finish line.** On this environment it appeared
  at 04:23:12, fifteen minutes *before* `Ready=True`. It is genuinely useful — it is where the
  kubeconfig comes from — but treating its existence as "the environment is up" gets you a platform
  that is still configuring.
- **A region showing as a registered cluster is not the finish line either.** `devops` registered at
  04:23:19, also fifteen minutes early.

## 5. Step 3 — get in

The platform address and the admin account name are on the `ACPPlatform`:

```bash
kubectl -n idp get acpplatforms.env.alauda.io "$PLATFORM" -o json \
  | jq -r '.status | {platformEndpoint, platformHost, platformAdminAccount, platformAccessAccount,
                      version: .version.versionStr, package: .package.name}'
```

Three secrets in namespace `idp` carry the rest. Keys only — read the values when you need them, and
do not paste them anywhere persistent:

| Secret | Keys | Use |
| :--- | :--- | :--- |
| `<platform>-admin` | `username`, `password`, `kind` | Console login |
| `<platform>-service-access` | `endpoint`, `token`, `kubeconfig` | **The ready-to-use kubeconfig** |
| `<machine>-ssh` | `username`, `password`, `port`, `privateKey`, `passPhrase` | Node-level access, one per machine |

The kubeconfig needs no browser flow:

```bash
kubectl -n idp get secret "$PLATFORM-service-access" \
  -o jsonpath='{.data.kubeconfig}' | base64 -d > env.kubeconfig
chmod 600 env.kubeconfig
```

Its server ends in `/kubernetes/global`. **The path segment selects the region**, so the business
cluster is the same file with that segment replaced:

```bash
sed 's#/kubernetes/global#/kubernetes/devops#' env.kubeconfig > env-devops.kubeconfig
```

## 6. Step 4 — verify the shape before you trust any test result

An environment that is `Ready` is not automatically the environment you meant to build. Four checks,
each of which has been wrong in practice:

```bash
# 1. Both regions registered and Running
kubectl --kubeconfig env.kubeconfig get clusters.platform.tkestack.io
# global   Running   1.35.6-acp.1
# devops   Running   1.35.6-acp.1

# 2. Node count, roles, OS mix, and IP family, per region
kubectl --kubeconfig env.kubeconfig        get nodes -o wide
kubectl --kubeconfig env-devops.kubeconfig get nodes -o wide
```

On the 2026-09-17 environment that returned: `global` with one master on RHEL 9.6; `devops` with
three masters on RHEL 9.6 plus one worker on RHEL 8.10; every `INTERNAL-IP` an IPv6 address and no
EXTERNAL-IP; Kubernetes `v1.35.6-acp.1` everywhere. That matches the tier template, which is the
point of running the check.

```bash
# 3. The ACP version and the installer package actually used
kubectl -n idp get acpplatforms.env.alauda.io "$PLATFORM" \
  -o jsonpath='{.status.version.versionStr} {.status.package.name} {.status.package.verificationStatus}{"\n"}'

# 4. Storage: is there any StorageClass at all?
kubectl --kubeconfig env-devops.kubeconfig get storageclass
```

Check 4 is the one people skip, and on the 2026-09-17 environment it returned **`No resources found`
on both regions** — no dynamic storage at all, not even TopoLVM, let alone ReadWriteMany. A
`CustomAcp` builds clusters; it does not lay down storage. The tier template's `rook-operator` entry
is not part of `CustomAcp`, so a hand-built environment needs a storage provider installed before
anything in the test asks for a PVC.

## 7. How a hand-built environment differs from the built-in env5 tier

Measured on the 2026-09-17 environment against
`task/prepare-acp-environment/0.1/environments/env5.yaml`. None of these are errors — but a report
filed as "env5" should be filed knowing about them.

| | Built-in env5 template | The hand-built environment |
| :--- | :--- | :--- |
| Installer | `intl/installer-core-v4.4.0-x86.tar` (international flavour, `-intl` component variants) | `installer-core-v4.4.0-x86.tar` |
| `devops` region network | kube-ovn **underlay**, `lb_type: vip`, plus one extra VIP | kube-ovn **overlay**, `entryAddr.type: loadbalancer` |
| `global` OS | RHEL 8.10 | RHEL 9.6 |
| Mixed OS in `devops` | one master and the worker on 8.10 | only the worker on 8.10 |
| Node naming | `hostname_as_nodename: true` | `hostnameAsNodename: false`, so nodes are named after their IPv6 address |
| `rook-operator` (RWX) | installed `after-platform-deploy` | not installed |
| Reclamation | the ReleaseTestPlan carries `iaas_ttl_hours` and a recycle policy | **none — nothing will delete it for you** |

The installer flavour is the one with teeth: the international installer carries `-intl` component
variants, which is also why env5 has its own product metadata snapshot (`env5.json`) in the catalog
rather than borrowing env2's.

## 8. Handing the environment to the release-test lane

The lane will not find your environment by itself. Two ways to make it use it:

1. **Adoption.** With no reuse handle, `prepare-acp-environment` looks for a Ready environment for
   that tier that is **less than 8 hours old** and adopts it. This is opportunistic, and an
   environment built by hand outside the lane's own naming may not be a candidate — **not verified
   for the hand-built case**.
2. **The reuse handle, which is explicit and is what you want.** `.tekton/to-release-test.yaml` binds
   an optional workspace to a Secret named per tier:

   ```text
   tektoncd-operator-release-existing-environment-<env-type>
   ```

   The Task short-circuits to `mode=reused` as soon as that directory holds an `address` plus either
   a `token` or `username`/`password` — before it reaches the "delete the prior environment" cleanup.
   The full key set written by a successful run is `address`, `token`, `username`, `password`,
   `kubeconfig`, `management-kubeconfig`, `env-type`, `environment-name`.

   Two rules come with it:

   - **`env-type` must match the tier you trigger.** The Task refuses to start otherwise
     (`env-type conflicts with the existing environment profile`). One Secret per tier, never shared.
   - **A handle reduced to only its `env-type` key is how you force a real rebuild.** `force-rebuild`
     alone is not enough: it skips *adoption*, while the handle is checked earlier and still
     short-circuits.

   Populating this Secret from a hand-built environment — rather than from a previous lane run's
   `environment` workspace — is the intended use, but has **not been verified end to end** at the time
   of writing. Check the `prepare-environment` log for `mode=reused` before believing it worked.

Then trigger the tier as usual (Release Process, section 7.5). env5 is an IDC tier, so the SOCKS
proxy parameter is mandatory.

## 9. Cleanup

**A hand-built environment has no TTL.** The lane's environments are reclaimed because the
`ReleaseTestPlan` carries `iaas_ttl_hours` and a recycle policy; a `CustomAcp` you created carries
neither. Seven machines stay allocated until someone deletes it.

Deleting the `CustomAcp` tears down the whole chain:

```bash
kubectl -n idp delete customacps.env.idp.alauda.io <name>
```

Before deleting, check that no reuse handle still points at it — a stale `address` in
`tektoncd-operator-release-existing-environment-env5` makes the next run fail on its first target API
call, an hour in, with an error that looks nothing like "the environment is gone".

## 10. Traps

1. **Treating the `service-access` Secret, or a region registering, as "ready".** Both happen about
   fifteen minutes early. Only `READY=True` on the `CustomAcp` is the finish line.
2. **Waiting out a machine that is not coming up.** Machines reach `ready` within about six minutes
   on a healthy build. Beyond ten, it is quota, subnet, or the provider.
3. **Assuming a hand-built env5 has storage.** Measured: no StorageClass at all on either region.
   TopoLVM, rook and ReadWriteMany are all things you install yourself.
4. **Assuming it will be reclaimed.** It will not. See section 9.
5. **Filing the report as plain "env5" without noting the installer flavour.** The international and
   domestic x86 installers are different packages with different component variants.
6. **Sharing one reuse handle between tiers.** The Task refuses to start, an hour into the queue.
7. **Looking for nodes by hostname.** With `hostnameAsNodename: false` they are named after their
   IPv6 address.

## 11. Keeping this page honest

Section 4.3, section 6 and the table in section 7 come from one measured environment built on
2026-09-17. The resource chain, the field meanings and the reuse-handle contract come from the live
CRs and from `.tekton/to-release-test.yaml` plus the catalog Task in
`https://code.alauda.io/platform-edge/pipelines/catalog-incubator`. Items marked "not verified" are
exactly that. When you build the next one, correct the timeline rather than adding a second one.
