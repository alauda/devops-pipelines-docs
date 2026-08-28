# Preserving TektonHub and its catalog on the 4.10.2 upgrade (DEVOPS-44544)

This document is the design of record for the release-4.10 behavior that lets one
4.10.2 codebase treat TektonHub differently on a fresh install versus an upgrade:

- **Fresh install** — do **not** deploy the in-cluster TektonHub by default. The Hub
  capability is served by the ArtifactHub shim (the shim / catalog-to-shim migration
  is DEVOPS-44537 and is out of scope here).
- **Upgrade** from a release that shipped TektonHub — **keep** the existing TektonHub
  **and** reuse its existing catalog artifacts, so Task/Pipeline references keep
  resolving. Both paths must work air-gapped.

The pre-4.10.2 default deleted an existing hub on upgrade, which broke those
references; this design replaces that default.

## Background: how the hub is deployed and how its catalog works

Understanding four mechanisms is required to see why the design is shaped the way it
is. All four are in the Alauda overlay (`.tekton/patches/`) or upstream.

1. **Deploy entrypoint (single).** Patch `0001-tektonconfig-deploys-hub-by-default`
   makes `TektonConfig` (profile `all`) create a `TektonHub` CR; patch
   `0019-default-disable-tektonhub-auto-deploy` gates that. There is no second place
   that creates a `TektonHub`.

2. **The catalog is not a database or PVC.** The hub API uses SQLite on an `emptyDir`
   (`SQLITE_DB=/mnt/git/sqlite.db`); the catalog is seeded by a `catalog-sidecar`
   **init container** (a native sidecar) in the `tekton-hub-api` Deployment. kodata
   ships only a **placeholder** catalog image (`.../tektoncd-hub-e2e/catalog:latest`).
   So "reuse the previous catalog" means "keep pulling the real catalog image that
   this environment already has", not "preserve a database".

3. **The image override path.** `TektonHub.Spec.Hub.Options`
   (`AdditionalOptions.Deployments[name]`) is applied as the **last** manifest
   transformer (`OptionsTransformer`), merging containers/init-containers by name and
   overriding a non-empty `Image`. `TektonConfig.Spec.Hub` propagates into `TektonHub`
   via `GetTektonHubCR`.

4. **InstallerSet rotation deletes the catalog ConfigMaps.** Patch `0010` keys the hub
   API InstallerSet's version annotation on `operatorVersion-releaseVersion`, so an
   operator upgrade makes the TektonHub reconciler **delete the old InstallerSet and
   create a new one**. Deleting the old InstallerSet fires its finalizer
   (`FinalizeKind` -> `DeleteResources`), which deletes every resource in the old
   InstallerSet's manifest — including the ~64 catalog ConfigMaps in `kube-public`.
   Patch `0015` makes that deletion honor `operator.tekton.dev/resource-policy: keep`,
   so a ConfigMap carrying that annotation survives the rotation.

   In a pre-4.10.2 install, 27 of the 64 catalog ConfigMaps already carry `keep`; the
   other 37 (24 `*-latest` tool-image CMs + 13 overview-template CMs) do not, so the
   rotation would delete them.

## Design

### 1. Three-state `AUTOINSTALL_TEKTONHUB` switch

An operator-level switch. The Go code reads it from the environment
(`os.Getenv("AUTOINSTALL_TEKTONHUB")`), and that environment variable is bound at
container start from the `tekton-config-defaults` ConfigMap (`tekton-operator`
namespace) via `configMapKeyRef`, mirroring the existing `AUTOINSTALL_COMPONENTS`
wiring (`config/operator/autoinstall-tektonhub.yaml`). The ConfigMap is the source of
truth: editing `AUTOINSTALL_TEKTONHUB` there and restarting the operator pod changes
the behavior. The default value in that ConfigMap is `preserve`. Normalized in
`AutoInstallTektonHubMode`
(`shared/tektonconfig/upgrade/autoinstall_mode.go`, shared to avoid an import cycle):

| Value | Meaning | Fresh install | Upgrade (had hub) |
| --- | --- | --- | --- |
| `preserve` (default / unset / empty / unrecognized) | observe-only: never create, never delete; keep an existing hub and wait until it is Ready | no hub | hub kept |
| `true` | ensure the hub (profile `all` only, else falls back to preserve) | hub deployed | hub kept |
| `false` | destructively remove any existing hub (opt-in only) | no hub | hub removed |

An unset/empty/unrecognized value maps to `preserve` (with a warning), so a typo can
never fall through to the destructive `remove` behavior. `observeExistingTektonHub`
implements preserve: it returns without acting on a fresh install, requeues while an
existing hub is not yet Ready, and never revives a hub that is being deleted.

### 2. Pre-upgrade migrations

Two version-gated `preUpgradeFunc`s (registered in `upgrade.go`). Both are scoped by
`resolveHubForPreserve`, which makes them strict no-ops unless this is a real
"upgrade with an existing hub": they do nothing when the switch is `false` (removal),
when there is no `TektonHub` CR (fresh install), or when the hub is being deleted.
This is what prevents a fresh install from stamping unrelated same-labelled
ConfigMaps, and prevents `false` from "protecting" catalog artifacts of a hub it is
about to remove.

- **`preserveExistingCatalogConfigMaps`** — in `kube-public`, selects catalog
  ConfigMaps by three intrinsic label EXISTS selectors (`operator.tekton.dev/tool-image`,
  `style.tekton.dev/overview-template-task`, `tekton.alaudadevops.io/template-type`;
  Kubernetes label selectors cannot wildcard keys, so each category needs its own), and
  for every one that lacks `keep`: stamps `operator.tekton.dev/resource-policy: keep`
  plus a marker `operator.tekton.dev/resource-policy-source: hub-catalog-preserve-on-upgrade`
  (which lets a later hub decommission find and clean these up), **and clears its
  `ownerReferences`**. Clearing the owner is the load-bearing part (see the regression
  Findings below): a pre-4.10.2 install created the `-latest` tool-image and
  `*-overview-template` ConfigMaps with a controller ownerReference to the hub-api
  InstallerSet (only the versioned tool-image and mail-template CMs ship `keep` built-in,
  so `injectOwner` left just those owner-less). On upgrade the hub-api InstallerSet
  rotates and is deleted, and Kubernetes owner-GC then cascades and deletes every
  ConfigMap it still owns — `keep` does **not** stop Kubernetes owner-GC, it only makes
  the operator's own manifestival finalizer skip. So the CM must be orphaned before the
  InstallerSet rotates; the rotation barrier (§3) sequences this ahead of the rotation.
  It only ever touches ConfigMaps that already exist.

- **`pinExistingHubCatalogImage`** — captures the real, environment-present
  `catalog-sidecar` image and pins it onto **both** `TektonConfig.Spec.Hub.Options`
  (source of truth) and the existing `TektonHub.Spec.Hub.Options` (preserve mode does
  not run `EnsureTektonHubExists`, so the config->hub propagation does not fire). The
  image is resolved in recovery-friendly order: an image already captured onto the
  CRs' options (idempotency / recovery from a partial prior run), then the live
  cluster — a ReplicaSet with available replicas (the catalog actually serving, which
  beats a higher-revision but never-Ready ReplicaSet from a failed rollout), then the
  Deployment's current spec, then the highest-revision real-image ReplicaSet. A
  substring guard (`hub-e2e/catalog`, robust to air-gap registry rewrites) prevents
  ever pinning the placeholder.

**Ordering.** `preserveExistingCatalogConfigMaps` is registered **before**
`pinExistingHubCatalogImage`, because pinning updates `TektonHub.Spec.Hub.Options`,
which changes the hub API InstallerSet spec hash and makes the hub controller rotate
that InstallerSet — after which Kubernetes owner-GC deletes any catalog ConfigMap still
owned by the old InstallerSet that has not yet been orphaned. Preserve (keep + orphan)
first.

### 3. The InstallerSet rotation barrier

> Shipped as patch `0021-installerset-rotation-barrier-on-upgrade.patch` (the two
> migrations of §2 ship as patch `0020`; the three-state switch as patch `0019`).

Ordering the two migrations closes the race where pinning *itself* triggers the
deletion. It does **not** close the deeper race: patch `0010`'s operator-version
rotation is driven by the **independent** TektonHub reconciler, which can delete the
old InstallerSet (and thus the 37 un-kept ConfigMaps, and re-render the Deployment to
the placeholder image) **before** the TektonConfig reconciler's pre-upgrade
migrations run at all. The two controllers race with no ordering guarantee.

The barrier removes that race by gating the **destructive** hub InstallerSet rotation
on a signal that the pre-upgrade migrations have completed. The signal is the upgrade
framework's own `TektonConfig.Status.PreUpgradeVersion`, which the framework sets to
the current operator version only **after every pre-upgrade function has succeeded**
(`updateUpgradeVersion`).

In the hub reconciler's rotation path (patch `0010`'s `checkIfInstallerSetExist` /
the delete-on-version-change branch): when an existing hub API InstallerSet is present
and its version differs from the current operator version (i.e. we are about to
rotate on upgrade), first check whether `PreUpgradeVersion == operatorVersion`. If
not, requeue and do **not** delete the old InstallerSet yet. Once pre-upgrade
completes, the barrier lifts and the rotation proceeds normally.

The barrier engages only when there is an existing InstallerSet **and** its version
differs (the upgrade window). It never blocks initial creation of a hub (e.g.
`AUTOINSTALL_TEKTONHUB=true` on a fresh install, where no old InstallerSet exists),
and after the upgrade window `PreUpgradeVersion == operatorVersion` holds
permanently, so it never affects steady-state operation.

#### Upgrade sequence (happy path)

1. The operator restarts at v4.10.2. Both reconcilers start.
2. The TektonHub reconciler wants to rotate (version changed). Barrier:
   `PreUpgradeVersion != v4.10.2` -> requeue. The old InstallerSet, the old Deployment
   (real catalog image), and all 64 ConfigMaps stay intact.
3. The TektonConfig reconciler runs pre-upgrade: `preserveExistingCatalogConfigMaps`
   stamps `keep` + marker on the 37 un-kept ConfigMaps; `pinExistingHubCatalogImage`
   reads the real catalog image from the still-live old Deployment and pins it onto
   `TektonConfig` and `TektonHub`. Pre-upgrade completes -> the framework sets
   `PreUpgradeVersion = v4.10.2`.
4. The TektonHub reconciler requeues, the barrier is now satisfied, and it rotates:
   the old InstallerSet's finalizer deletes its manifest resources, but the 37
   ConfigMaps now carry `keep` and survive; the new InstallerSet renders from the new
   kodata plus the pinned real image (Options is the final transformer, overriding the
   placeholder), so the new Deployment pulls the real, environment-present image.

Result: the hub is preserved, the catalog ConfigMaps are preserved, and the catalog
image is real.

#### Deadlock / stuck-state analysis

The barrier's requeue cannot deadlock, because `PreUpgradeVersion` is guaranteed to
reach `operatorVersion` independently of the hub:

- Pre-upgrade completes when **all** pre-upgrade functions return `nil`; only then is
  `PreUpgradeVersion` set. None of the upstream pre-upgrade functions
  (reset-conditions, pipeline-properties, result-config, results-TLS, pruner) touch
  the hub. Neither migration waits on hub readiness or on the InstallerSet rotating:
  `preserveExistingCatalogConfigMaps` only reads/patches ConfigMaps, and
  `pinExistingHubCatalogImage` only reads the Deployment/ReplicaSets and patches the
  two CRs. So **no pre-upgrade function depends on the thing the barrier blocks** —
  there is no circular wait. Pre-upgrade completes, `PreUpgradeVersion` is set, the
  barrier lifts.
- Blocking the rotation does not stall the TektonConfig reconciler either: its hub
  switch (`observeExistingTektonHub`) runs *after* pre-upgrade (which requeues until
  complete), and once the barrier lifts the hub becomes Ready, so the observe step
  converges.

The one genuine stuck candidate is `pinExistingHubCatalogImage` retrying (returning a
retryable error) if it can never find a real catalog image — and the barrier
**eliminates** it rather than adding it. Because the barrier keeps the old Deployment
(real image) alive throughout pre-upgrade, "no real image found" is no longer an
ambiguous transient-rotation artifact; it is an unambiguous signal that the hub
genuinely has no usable catalog. So under this design `pinExistingHubCatalogImage`
skips with a warning (returns `nil`) on a genuine absence rather than retrying
forever. The barrier therefore makes the upgrade both race-free **and** free of the
retry-forever stuck state.

### 4. kodata placeholder

The kodata `catalog-sidecar` image stays a placeholder (there is no released catalog
image to ship), and `config/tekton-hub` is unchanged. The upgrade path is covered by
the pin above; a fresh install does not deploy the hub. The only consumer of the
placeholder is an explicit `AUTOINSTALL_TEKTONHUB=true` fresh install, which is a
test/special scenario.

## Testing

- **Unit** — three-state switch normalization; `observeExistingTektonHub`
  (not-found / not-ready-requeue / ready / deleting); `resolveHubForPreserve`
  scoping; image resolution incl. the available-ReplicaSet preference, placeholder
  guard, and Options recovery; ConfigMap keep+marker with fresh-install/removal
  no-ops; and the barrier gate.
- **e2e (backlog)** — an install-old-hub -> upgrade lane asserting the TektonHub
  UID survives and is not deleting, the live `tekton-hub-api` `catalog-sidecar` image
  equals the pre-upgrade image (not the placeholder), and catalog ConfigMaps that
  lacked `keep` survive with the marker. Tracked in `.tekton/patches/README.md`.

## Regression: scope and method

The three upgrade scenarios below are the regression suite for this design. Each was
exercised end-to-end on a live global cluster (release-4.10, OLM-managed operator)
against `v4.10.2-pr...--44544-preserve-hux`. Every scenario carries the same mandatory
acceptance: **a `resolver: hub` pipeline still resolves and runs successfully after the
upgrade** — a green upgrade with a broken resolver is a failure.

### Scope — the three scenarios

| # | Pre-upgrade state | Post-upgrade expectation | Mandatory check |
| --- | --- | --- | --- |
| 1 | in-cluster TektonHub present | hub kept + its catalog artifacts reused | pipeline still runs |
| 2 | scenario 1, then manually switch to the ArtifactHub shim | hub resolver serves from the shim | pipeline still runs |
| 3 | no in-cluster hub (`profile != all`) + shim only | stays on the shim; the hub is not force-created | pipeline still runs |

### Method

- **Operator version transitions (OLM).** The platform `ModuleInfo` *reflects* the
  installed CSV; it does not drive OLM. So a downgrade/upgrade is done at the OLM layer:
  delete the CSV + Subscription, re-create the Subscription with the target
  `startingCSV`, then approve the Manual `InstallPlan`. (Patching `ModuleInfo.spec.version`
  is reverted by the marketplace controller and does not trigger a rollout.)
- **Establishing the no-hub pre-state (scenario 3).** On the old baseline (v4.10.1) the
  in-cluster hub is gated on `TektonConfig.spec.profile == all` (upstream, pre-`0019`),
  and `EnsureTektonHubExists` runs only during a `TektonConfig` reconcile. Set the
  profile to a non-`all` value (e.g. `basic`) and delete the `TektonHub` CR — it is then
  not recreated. (Changing the profile resets `hubresolver-config` to the public
  default, so re-point `TektonConfig.spec.pipeline.hub-resolver-config` at the shim
  service afterwards.)
- **Shim install/switch.** Install the ArtifactHub shim via a `ClusterPluginInstance`
  (`spec.pluginName: artifacthub-shim`); a hand-created `ModuleInfo` is normalized/pruned
  by the cluster transformer and never deploys. The hub resolver is pointed at the shim
  through `TektonConfig.spec.pipeline.hub-resolver-config`.
- **Assertions per scenario.**
  - Scenario 1: the `TektonHub` UID is unchanged and not deleting; the live
    `tekton-hub-api` `catalog-sidecar` image equals the pre-upgrade real image (not the
    placeholder — this is `pinExistingHubCatalogImage`'s output); `TektonConfig` reaches
    `PostUpgrade`/`Ready` with no `tls_hostname_override` livelock.
  - Scenarios 2 & 3: the `TektonHub` is absent (scenario 3) and **stays** absent across
    a forced `TektonConfig` reconcile (preserve mode does not force-create it); a
    `resolver: hub` PipelineRun Succeeds and its
    `TaskRun.status.provenance.refSource.uri` points at the shim API service — proving
    resolution went through the shim, not a stale cache.

### Findings / open items from the regression

- **Versioned catalog ConfigMaps are preserved as designed.** The
  `catalog-tool-image-<tool>-<version>` CMs — the tool -> image-version mappings that
  Task resolution actually consumes — ship with `resource-policy: keep` built in and
  survive the InstallerSet rotation (and even a direct `TektonHub` CR deletion).
- **The `*-latest` and `*-overview-template` CMs were deleted on upgrade — root cause
  found and fixed (Kubernetes owner-GC, not the finalizer).** A controlled reproduction
  (downgrade to 4.10.1, natively deploy the hub + real catalog, then upgrade to 4.10.2
  while streaming the operator log) settled it with a full evidence chain:
  - **The selectors are not the gap.** The natively-published `-latest` CMs carry
    `operator.tekton.dev/tool-image` and the `*-overview-template` CMs carry
    `style.tekton.dev/overview-template-task`, so all 30 un-kept CMs match a preserve
    selector; the operator log confirms preserve stamped keep on all of them
    (`30 newly kept out of 55`), yet they were still deleted.
  - **The killer is Kubernetes garbage collection via ownerReferences, which `keep` does
    not stop.** The original v4.10.1 `-latest`/overview CMs are owned (controller,
    blockOwnerDeletion) by the hub-api InstallerSet, because `injectOwner`
    (`tektoninstallerset/transformer.go`) only skips owner injection for resources that
    *already* carry `keep` — the versioned tool-image and mail-template CMs ship `keep`
    built-in (so they were left owner-less and survive), the `-latest`/overview CMs did
    not. On upgrade the hub-api InstallerSet rotates (patch `0010`) and is deleted, and
    K8s owner-GC cascades and deletes every CM it owns. `keep` only makes the operator's
    manifestival finalizer skip (`install.go`) — the log shows **zero** finalizer
    skip/delete lines for these CMs, confirming they were removed by apiserver-side GC,
    not by the operator.
  - **Fix.** `preserveExistingCatalogConfigMaps` now also **clears `ownerReferences`**
    (orphans the CM) when it stamps keep — see `patchConfigMapKeepPolicy`. Once orphaned,
    the CM behaves exactly like the built-in-keep versioned CMs and survives the
    InstallerSet rotation; the rotation barrier (§3) guarantees preserve runs before the
    rotation, so clearing the owner is race-free. `keep` is still stamped (it blocks the
    finalizer, stops `injectOwner` from re-adding an owner, and marks the CM for later
    hub-decommission cleanup) — the fix *adds* owner-clearing, it does not replace keep.

## Related tickets

- **DEVOPS-44537** — upgrade migration of the catalog to the ArtifactHub shim and the
  eventual hub decommission (which cleans up via the `resource-policy-source` marker).
- **DEVOPS-44525** — ArtifactHub shim v1.0.0.

This change only guarantees that after an upgrade the hub and its catalog are "still
there, still usable, and pulling an image that exists in this environment."
