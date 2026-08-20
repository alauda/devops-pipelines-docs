---
weight: 11
status: proposed
title: Preserve Alauda-patched fields under TektonConfig `options` after the switch to generated CRDs
creation-date: "2026-06-29"
category: docs
authors:
  - "@qingliu"
---

## Summary

The Alauda overlay adds an `ingress` field to `TektonConfig`'s `*.options`
(`AdditionalOptions`) via patch
`.tekton/patches/0008-support-ingress-as-additional-options.patch`. This field
lets operators override the generated Ingress objects (e.g. set
`ingressClassName: global-alb2`) when deploying on a global cluster, as
documented in `docs/en/how_to/deploy_global.mdx`.

After the upstream submodule was bumped from `release-v0.78.x` to `v0.80.x`
(Alauda commit `f13d6aa3`, which moved the submodule from upstream
`d3742fb7` to `5c9be326`), this field is **silently dropped by the
Kubernetes API server**. `kubectl apply` / `patch` of
`spec.pipeline.options.ingress` now reports
`unknown field "spec.pipeline.options.ingress"` and the value never reaches
the controller. `docs/en/how_to/deploy_global.mdx` therefore documents a knob
that no longer works on shipped builds.

This TEP records the root cause and proposes a minimal, upgrade-resilient fix:
re-open the `options` subtree of the `TektonConfig` CRD with
`x-kubernetes-preserve-unknown-fields: true`, delivered as a **kustomize
JSON6902 patch in the Alauda overlay `config/operator`** so it is re-applied to
the rendered CRD on every build without touching the upstream submodule.

## Motivation

`options.ingress` is the only supported, documented way to make the
`tektoncd-enhancement-api` / `tektoncd-results-api` / `hubs-wrapper` Ingress
objects usable on a global cluster, where the ingress class is `global-alb2`
rather than the operand default `cpaas-system`. With the field pruned:

- The capabilities API (`/tektoncd-enhancement/apis/v1alpha1/capabilities`)
  and the Results API are unreachable through the platform ALB — the ALB has
  no route for a `cpaas-system`-class Ingress and redirects to
  `/console-portal` (HTTP 302). The Pipelines-as-Code Repository UI, gated on
  that capabilities response, never unlocks.
- The documented global-cluster deployment procedure is broken with no
  supported replacement; operators are forced into out-of-band
  `kubectl patch ingress ...`, which is reverted whenever the owning
  `TektonInstallerSet` is recreated.

### Goals

- Restore the ability to set `spec.<component>.options.ingress` (and any other
  Alauda-patched `AdditionalOptions` field) on shipped builds.
- Keep the fix working across future upstream bumps with minimal maintenance
  and minimal merge-conflict risk.
- Keep `docs/en/how_to/deploy_global.mdx` accurate.

### Non-Goals {#non-goals}

- Changing how the Ingress objects themselves are generated, or changing the
  operand default ingress class.
- Upstreaming `AdditionalOptions.Ingress` to tektoncd/operator (tracked
  separately; this TEP only restores the existing Alauda behavior).
- Fixing the runtime `kubectl patch ingress` workaround — it is a stopgap, not
  part of this design.

### Use Cases {#use-cases}

- A cluster administrator deploying `tektoncd-pipelines` /
  `tektoncd-results` on the **global** cluster follows
  `deploy_global.mdx` and sets `options.ingress.<name>.spec.ingressClassName:
  global-alb2`; the value is accepted and the operator reconciles the Ingress
  with the correct class.

### Requirements

- The fix must live in an artifact that is actually installed on the cluster
  (the CRD applied to the API server), not only in the operator binary.
- The fix must survive `make` / build-time regeneration of upstream CRDs.
- The fix must not regress strict validation for unrelated `TektonConfig`
  fields outside `options`.

## Proposal

Add `x-kubernetes-preserve-unknown-fields: true` to the `options` object of
every component in the `TektonConfig` CRD. This makes the API server **keep**
unknown sub-fields of `options` (such as `ingress`) instead of pruning them,
while leaving the rest of the schema strict. The controller binary already
understands `options.ingress` (patch 0008), so once the value is preserved by
the API server, reconciliation works exactly as it did before the v0.80.x bump.

This is delivered as a **kustomize JSON6902 patch in the Alauda overlay
`config/operator`** (the same overlay that already carries the
`add-rbac-verb-for-enhancement`, `pac-operator-args-patch`, etc. patches). The
overlay patches the rendered CRD that the operator installs
(`config/operator/base/release.yaml` → `kustomize build config/operator`), so
the fix:

- does **not** touch the `upstream` submodule or `.tekton/patches/`, so it
  never produces a `.rej` when upstream regenerates its CRDs;
- rides on top of whatever `release.yaml` is vendored, build after build;
- lives next to the other operator-overlay patches, where reviewers expect it.

### Notes and Caveats {#notes-and-caveats}

- The pruning happens at the API server, governed by the **installed CRD
  schema** — not by the operator binary. A binary that has the Go field is
  necessary but not sufficient; the API server prunes `options.ingress` before
  the controller ever reads it. Hence the fix must change the CRD.
- What actually gets installed: the Alauda repo vendors the rendered operator
  manifest at `config/operator/base/release.yaml` (which contains the strict
  `tektonconfigs` CRD), and `kustomize build config/operator` is the install
  artifact. The chosen fix patches *that* rendered CRD via the overlay, so it is
  independent of how `release.yaml` is refreshed and of the upstream submodule.
- Upstream itself now carries two CRD shapes — the strict
  `config/base/generated-crds/...tektonconfigs.yaml` (what flows into
  `release.yaml`) and the OLM bundle manifest, which is still a blanket
  top-level `x-kubernetes-preserve-unknown-fields: true` (would not exhibit the
  bug). The OLM bundle path is not the one in use here; if it ever is, apply the
  equivalent preserve-unknown there too.
- `properties` and `x-kubernetes-preserve-unknown-fields: true` are allowed to
  coexist on the same object in a structural schema: declared properties are
  still validated, and unknown ones are preserved rather than pruned. This is
  the same contract the pre-v0.80 hand-written CRD provided for the whole
  schema; here it is scoped narrowly to `options`.

## Design Details {#design-details}

### Root cause (evidence)

- `AdditionalOptions.Ingress` (`json:"ingress,omitempty"`) is added by
  `.tekton/patches/0008-support-ingress-as-additional-options.patch`,
  introduced in Alauda commit `e9e11b5d` / PR #50 (2025-02-27). The patch
  touches only three Go files
  (`pkg/apis/operator/v1alpha1/additional_options.go`,
  `pkg/reconciler/common/transformer_additional_options.go`,
  `pkg/reconciler/common/targetnamespace.go`) and **never updates any CRD
  YAML**.
- Before the bump (upstream `d3742fb7`, used by Alauda `release-4.12` and
  `main`), the `TektonConfig` CRD schema was a single top-level
  `x-kubernetes-preserve-unknown-fields: true`. Any field, including
  `options.ingress`, was accepted. This is why the feature worked on
  `release-4.12`.
- The upstream **tree** at `5c9be326` carries the "use generated CRDs in
  kustomize" topology: `config/base/kustomization.yaml` references
  `generated-crds/operator.tekton.dev_tektonconfigs.yaml`, a strict
  controller-gen schema whose `options` enumerates properties and is **not**
  preserve-unknown. (The manual→generated migration landed across a range of
  upstream commits; the tip commit `5c9be326`, 2026-06-23, "Cleanup manual CRDs
  and use generated CRDs in kustomize", has only a 1-line diff itself — it is
  the tree state the submodule pins, not a single switch commit.) The old tree
  at `d3742fb7` instead had a hand-written CRD that was a single blanket
  top-level `x-kubernetes-preserve-unknown-fields: true`.
- Alauda commit `f13d6aa3` (2026-06-25, "upgrade upstream operator
  release-v0.78.x to v0.80.x") bumped the `upstream` submodule
  `d3742fb7 -> 5c9be326`, pulling the strict-CRD tree into the build. Remote
  submodule-pointer ground truth at time of writing (two remotes, out of sync):
  `origin/main` (code.alauda.io, the primary) **already** pins the strict
  `5c9be326` — i.e. the regression is **already live on the primary `main`**;
  `origin/release-4.12` and the GitHub mirror `alaudadevops/main` still pin the
  permissive `d3742fb7` (a build from those still accepts `options.ingress`).
  The affected environment build `eba812e` also carries `f13d6aa3`/`5c9be326`.
  So this TEP fixes a regression already on `main`, not a future risk; it should
  land on `main` (and ride along with any `release-4.12` v0.80 bump).

Observed on the live global cluster: the installed CRD
`tektonconfigs.operator.tekton.dev` has, for every component,
`spec.<component>.options` with `x-kubernetes-preserve-unknown-fields` unset
and an explicit property list of
`configMaps, deployments, disabled, horizontalPodAutoscalers, statefulSets,
webhookConfigurationOptions` — no `ingress`.

### The change

Add a JSON6902 patch that sets
`.../options/x-kubernetes-preserve-unknown-fields: true` for **every** `options`
(`AdditionalOptions`) object in the `TektonConfig` CRD. There are **eleven**:
the nine top-level component options —
`chain`, `dashboard`, `hub`, `multiclusterProxyAAE`, `pipeline`, `result`,
`scheduler`, `tektonpruner`, `trigger` — **plus the two platform PaC-settings
options** `spec.platforms.kubernetes.pipelinesAsCode.options` and
`spec.platforms.openshift.pipelinesAsCode.options`.

The two PaC ones matter especially here: `PACSettings.Options
AdditionalOptions` (`upstream/pkg/apis/operator/v1alpha1/openshiftpipelinesascode_types.go`)
is copied from `TektonConfig` into `OpenShiftPipelinesAsCode`
(`.../tektonconfig/extension/pipelinesascode.go`) and consumed via
`ExecuteAdditionalOptionsTransformer`
(`.../openshiftpipelinesascode/transform.go`). Omitting them would still prune
`spec.platforms.{kubernetes,openshift}.pipelinesAsCode.options.ingress`.

New file `config/operator/preserve-unknown-options.yaml` (RFC6902 op list):

```yaml
- op: add
  path: /spec/versions/0/schema/openAPIV3Schema/properties/spec/properties/chain/properties/options/x-kubernetes-preserve-unknown-fields
  value: true
- op: add
  path: /spec/versions/0/schema/openAPIV3Schema/properties/spec/properties/dashboard/properties/options/x-kubernetes-preserve-unknown-fields
  value: true
- op: add
  path: /spec/versions/0/schema/openAPIV3Schema/properties/spec/properties/hub/properties/options/x-kubernetes-preserve-unknown-fields
  value: true
- op: add
  path: /spec/versions/0/schema/openAPIV3Schema/properties/spec/properties/multiclusterProxyAAE/properties/options/x-kubernetes-preserve-unknown-fields
  value: true
- op: add
  path: /spec/versions/0/schema/openAPIV3Schema/properties/spec/properties/pipeline/properties/options/x-kubernetes-preserve-unknown-fields
  value: true
- op: add
  path: /spec/versions/0/schema/openAPIV3Schema/properties/spec/properties/result/properties/options/x-kubernetes-preserve-unknown-fields
  value: true
- op: add
  path: /spec/versions/0/schema/openAPIV3Schema/properties/spec/properties/scheduler/properties/options/x-kubernetes-preserve-unknown-fields
  value: true
- op: add
  path: /spec/versions/0/schema/openAPIV3Schema/properties/spec/properties/tektonpruner/properties/options/x-kubernetes-preserve-unknown-fields
  value: true
- op: add
  path: /spec/versions/0/schema/openAPIV3Schema/properties/spec/properties/trigger/properties/options/x-kubernetes-preserve-unknown-fields
  value: true
- op: add
  path: /spec/versions/0/schema/openAPIV3Schema/properties/spec/properties/platforms/properties/kubernetes/properties/pipelinesAsCode/properties/options/x-kubernetes-preserve-unknown-fields
  value: true
- op: add
  path: /spec/versions/0/schema/openAPIV3Schema/properties/spec/properties/platforms/properties/openshift/properties/pipelinesAsCode/properties/options/x-kubernetes-preserve-unknown-fields
  value: true
```

Registered in `config/operator/kustomization.yaml` under `patches:`:

```yaml
  - path: ./preserve-unknown-options.yaml
    target:
      group: apiextensions.k8s.io
      version: v1
      kind: CustomResourceDefinition
      name: tektonconfigs.operator.tekton.dev
```

This was validated against the current tree: `kustomize build config/operator`
renders the `tektonconfigs` CRD from 1438 to 1449 lines (exactly +11, one
preserve-unknown line per `options` object), with all 11 `options` blocks and
the rest of the schema untouched, and `kustomize build` exits 0 (every JSON6902
`add` target resolved, confirming all eleven `options` objects exist — a missing
path would fail the build).

`versions/0` assumes the single `v1alpha1` version the CRD currently ships
today. If upstream adds another served version, the existing `/versions/0` ops
would **not** fail — they would silently leave the new version strict. The fix
must therefore add an op block per served version index, and the CI assertion
must check preserve-unknown on **every** served version (not merely count total
ops vs. delta).

### The change, part 2 — component CRDs (TektonPipeline, TektonResult)

Patching the `tektonconfigs` CRD alone is **necessary but not sufficient**.
`AdditionalOptions` does not stay in `TektonConfig`: the config controller copies
`TektonConfig.spec.<component>.options` into the matching component CR
(`GetTektonPipelineCR` does a whole-struct `Pipeline: config.Spec.Pipeline`, and
`UpdatePipeline` re-syncs `Spec.Options` on change). The
`AdditionalOptions` transformer that actually rewrites the managed Ingress reads
the **child** CR's `spec.options`, not the parent's. Each component CRD
(`tektonpipelines`, `tektonresults`, ...) carries its **own** controller-gen
`spec.options` schema, which enumerates the same six known properties
(`configMaps, deployments, disabled, horizontalPodAutoscalers, statefulSets,
webhookConfigurationOptions`) and is **not** preserve-unknown. So even with the
parent fixed, the API server prunes `options.ingress` again on the write to the
child CR, the transformer reads an empty `Ingress` map, and the annotation never
reaches the managed Ingress.

This was caught by the product e2e scenario
`tektoncd-enhancement-ingress-additional-options-001`: a live capture showed
`TektonConfig.spec.pipeline.options.ingress` carrying the injected annotation
while `TektonPipeline.spec.options.ingress` stayed empty the entire reconcile
window — the parent kept it, the child dropped it.

The fix is the same preserve-unknown, applied to the **component** CRDs' top-level
`spec.options` — but **scoped to the components that actually manage an Ingress**,
not blanket-applied. Only two do, and only their `options.ingress` is the
documented global-cluster knob (`docs/en/how_to/deploy_global.mdx`):

- `tektonpipelines.operator.tekton.dev` — manages `hubs-wrapper` and
  `tektoncd-enhancement-api` Ingresses (`spec.pipeline.options.ingress`).
- `tektonresults.operator.tekton.dev` — manages the `tektoncd-results-api`
  Ingress (`spec.result.options.ingress`).

The remaining component CRDs (`chain`, `dashboard`, `hub`, `multiclusterProxyAAE`,
`pruner`, `scheduler`, `trigger`) ship no Ingress in their kodata, so
`options.ingress` is never set for them and they need no preserve-unknown.

New file `config/operator/preserve-unknown-component-options.yaml` (a single
JSON6902 `add` of `.../spec/properties/options/x-kubernetes-preserve-unknown-fields:
true`, identical path for both), registered in `kustomization.yaml` with one
`target` per component CRD (tektonpipelines, tektonresults). Validated render:
`kustomize build config/operator` goes from 105 to 107 preserve-unknown lines
(exactly +2), with only the pipeline and result component `options` gaining it.

### Why JSON6902 and not a strategic-merge patch

A strategic-merge patch on this CRD is **destructive** under this repo's current
kustomize setup and was rejected after testing: because kustomize (without
custom OpenAPI merge-key configuration, which `config/operator/kustomization.yaml`
does not define) does not deep-merge the `spec.versions[]` list schema, a
strategic-merge overlay **replaces** the `versions[0].schema` subtree with only
the fields in the patch. In testing this collapsed the rendered `tektonconfigs` CRD from 1438
lines to ~60 — i.e. it wiped the real schema. JSON6902 `op: add` is surgical: it
inserts a single key under an existing object without disturbing siblings, which
is why the validated render stays intact at 1449 lines.

### Why this overlay and not `.tekton/patches/`

`.tekton/patches/` patches are diffs applied to the **upstream submodule's**
source files. Patching the generated CRD there
(`config/base/generated-crds/operator.tekton.dev_tektonconfigs.yaml`) works but
is fragile: that file is regenerated by upstream's `controller-gen`, so a
context-bearing `.patch` conflicts (`.rej`) on most bumps. The `config/operator`
kustomize overlay instead patches the **rendered** CRD declaratively by object
identity and JSON pointer, so it is far more stable across upstream changes.

### Why not regenerate the full `ingress` sub-schema

Adding the full `ingress` sub-schema (a complete `networking.k8s.io/v1`
`Ingress` object) would make the CRD strictly validate `options.ingress`, but it
is a large, deeply-nested block to maintain, and it only covers `ingress` —
every future Alauda-added `options` field would need the same treatment.
`x-kubernetes-preserve-unknown-fields: true` is one op per component and covers
all current and future patched `options` fields at once.

## Design Evaluation {#design-evaluation}

### Reusability

Reuses the existing `config/operator` kustomize overlay (the same one that
already carries the rbac / pac-operator-args patches) and the existing
`AdditionalOptions.Ingress` controller logic (patch 0008). No new machinery.

### Simplicity

Minimal: eleven single-line additions (one per `options` object), expressed as
one kustomize JSON6902 patch. Restores behavior users already had on
`release-4.12`.

### Flexibility

No new coupling. The change is confined to the `options` subtree of one CRD.

### Conformance

`options` (`AdditionalOptions`) is explicitly an open, operator-facing
extension point ("additional fields ... will be updated on the manifests").
Marking it preserve-unknown matches that intent. Fields outside `options`
remain strictly validated.

### Risks and Mitigations {#risks-and-mitigations}

- **Loss of strict validation inside `options`** — a typo such as
  `options.ingres` would be accepted and silently ignored instead of rejected.
  Mitigation: this is precisely the pre-v0.80 behavior; the blast radius is the
  `options` subtree only. Documentation (`deploy_global.mdx`) shows the exact
  expected keys.
- **Two CRD representations drift** — if the OLM bundle path is ever used,
  behavior could differ. Mitigation: keep both representations consistent in
  the patch, or explicitly scope to the kustomize path and note it.
- **Upstream may later add native support / change the options schema** — if
  upstream makes `options` preserve-unknown or adds `ingress` natively, this
  patch becomes a no-op or a clean conflict. Mitigation: the patch is small and
  easy to retire; revisit on each upstream bump.

### Drawbacks

Slightly weaker schema validation for `options`. Accepted as the deliberate
trade-off for an extension point.

## Alternatives

- **A. Re-run controller-gen after applying patches.** The upstream submodule
  points at the real `tektoncd/operator`, so regenerated CRDs cannot be
  committed upstream and must still be carried as a patch — codegen does not
  remove the patch, it only produces a larger, controller-gen-version-sensitive
  one, and adds a build-time toolchain dependency. Rejected as high-cost.
- **B. `.tekton/patches/` patch on the upstream generated CRD.** Add the same
  preserve-unknown lines to
  `config/base/generated-crds/operator.tekton.dev_tektonconfigs.yaml` in the
  submodule. Works, but it is a context-bearing diff against a controller-gen
  output, so it `.rej`s on most upstream bumps. The `config/operator` kustomize
  overlay (chosen) avoids this.
- **C. Strategic-merge kustomize patch.** Rejected — destructive: kustomize
  replaces the `versions[0].schema` subtree (collapsed the CRD 1438 → ~60 lines
  in testing). See Design Details.
- **D. Patch the full `ingress` sub-schema for strict validation.** Correct and
  strict, but a large block to maintain and covers only `ingress`. Can be
  layered on later if strict validation / UI form support for `ingress` is
  wanted.
- **E. Runtime `kubectl patch ingress`/CRD on the cluster.** Stopgap only;
  reverted by the operator on InstallerSet recreation / restart. Useful to
  unblock the environment immediately, not a fix.

## Implementation Plan {#implementation-plan}

1. Add `config/operator/preserve-unknown-options.yaml` (the eleven-op JSON6902
   list above) and register it under `patches:` in
   `config/operator/kustomization.yaml` targeting CRD
   `tektonconfigs.operator.tekton.dev`.
2. Assert `kustomize build config/operator` succeeds and the rendered
   `tektonconfigs` CRD gains exactly eleven `x-kubernetes-preserve-unknown-fields:
   true` lines (one per `options` object) with no other schema change.
3. Rebuild the operator image / kodata; confirm the packaged CRD contains the
   added lines.
4. Roll out to the affected environment; run the Test Plan.
5. Confirm `docs/en/how_to/deploy_global.mdx` wording still matches (the field
   is now preserved, validated loosely).

### Test Plan {#test-plan}

- **Render assertion (offline, already validated):**
  `kustomize build config/operator` renders the `tektonconfigs` CRD at +11 lines
  vs. baseline, all 11 `options` blocks carrying preserve-unknown, exit 0.
  Suitable as a CI check.
- **Schema acceptance (server dry-run, on a cluster with the patched CRD):**
  `kubectl patch tektonconfigs config --type merge --dry-run=server -p
  '{"spec":{"pipeline":{"options":{"ingress":{"tektoncd-enhancement-api":{"spec":{"ingressClassName":"global-alb2"}}}}}}}'`
  must succeed **without** the `unknown field "spec.pipeline.options.ingress"`
  warning, and a read-back must show the value retained.
- **Controller behavior:** after applying the above for real, the operator
  reconciles `Ingress/tektoncd-enhancement-api` to
  `ingressClassName: global-alb2`; the ALB registers a rule and
  `/tektoncd-enhancement/apis/v1alpha1/capabilities` returns HTTP 200.
- **Negative scope check:** confirm fields outside `options` are still rejected
  when invalid (strict validation preserved).

### Upgrade and Migration Strategy {#upgrade-and-migration-strategy}

No data migration. Existing `TektonConfig` resources are unaffected.
Environments already broken by the v0.80.x bump regain the field once the
rebuilt operator is rolled out. As an immediate unblock before the rebuild,
operators may `kubectl patch ingress <name> -n tekton-pipelines --type merge
-p '{"spec":{"ingressClassName":"global-alb2"}}'` (stopgap; not upgrade-safe).

### Implementation Pull Requests {#implementation-pull-requests}

- TBD

## References

- Patch introducing the Go field: `.tekton/patches/0008-support-ingress-as-additional-options.patch`,
  PR https://github.com/AlaudaDevops/tektoncd-operator/pull/50 ,
  commit https://github.com/AlaudaDevops/tektoncd-operator/commit/e9e11b5deadee271756510b283b1ff7b6f073276
- Upstream submodule bump (regression trigger): Alauda commit
  https://github.com/AlaudaDevops/tektoncd-operator/commit/f13d6aa3
- Upstream "use generated CRDs" change:
  https://github.com/tektoncd/operator/commit/5c9be326329048f30555acf84e39245be0b3f4b1
  (previous pinned commit
  https://github.com/tektoncd/operator/commit/d3742fb732776c0d32de760b212b5a05c02018f8 )
- Global-cluster deployment guide: `docs/en/how_to/deploy_global.mdx`
- Customize options guide: `docs/en/configure/customize_options.mdx`
