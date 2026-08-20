# SPEC-FIX-DEVOPS-44435: Unblock the 4.0.x → 4.13 OLM upgrade (operand CRD `required` tightening incompatible with existing CRs)

Status: draft (pending review + owner sign-off)
Owners: @qingliu (dev) / @TBD-operator-qe
Issue: DEVOPS-44435 https://jira.alauda.cn/browse/DEVOPS-44435 ; related DEVOPS-44427 https://jira.alauda.cn/browse/DEVOPS-44427 (same class, lighter, already handled by its overlay fix)
Related: SPEC-X-operator-lifecycle (upgrade / install cross-cutting)
Upstream: github.com/tektoncd/operator (v0.80.0 CRD schema; upstream commit 6ae9dae4b "fix: options field should be optional in all components" https://github.com/tektoncd/operator/commit/6ae9dae4b only added `+optional` to `options`, and it is not yet in the v0.80.0 tag)
API touched: operator.tekton.dev/v1alpha1 — TektonConfig and each operand CRD (TektonPipeline/TektonTrigger/TektonChain/TektonResult/TektonPruner/TektonHub/TektonMulticlusterProxyAAE/TektonScheduler/ManualApprovalGate)

---

## 1. Summary

Upgrading tektoncd-operator from 4.0.x (validated here on 4.0.17 / operand v0.74.1) to 4.13 (operand v0.80.0) via OLM leaves the InstallPlan `Failed` and the CSV stuck `Pending` — the upgrade is completely blocked. The root cause is that the v0.80.0 CRD schema marks several `spec` fields of TektonConfig and every operand CRD as **required**, while the pre-existing older CRs lack those fields. When OLM updates a CRD it enforces "the new schema must not invalidate existing CRs", so it refuses the CRD update and the whole InstallPlan fails.

This spec adopts **A+: generic normalization** — after downloading the upstream `release.yaml`, recursively strip every `required` array under the `spec` schema subtree of all `operator.tekton.dev` CRDs, so field-less older CRs validate cleanly. It is accompanied by: deleting the now-redundant `required` patches in the existing overlay, adding a CI guard, and adding an "upgrade-from-oldest-supported-baseline" e2e as a long-lived regression net. Forward compatibility (a later upgrade to a still-`required` community version is not blocked) is guaranteed **primarily by keeping the A+ strip as a permanent build step** (uniform across all CRDs, independent of runtime behavior); the transitional operator's data self-heal is only a **partial** bonus — source review confirms TektonConfig and most operands self-heal, but **ManualApprovalGate does not** (see §5.4), so we must not rely on self-heal alone.

---

## 2. Motivation

### 2.1 Symptom
- On a 4.0.17 environment (profile=all), upgrading the operator to 4.13: InstallPlan `Failed`, CSV `Pending`.
- First error (reproduced):
  ```
  error validating existing CRs against new CRD's schema for "tektonconfigs.operator.tekton.dev":
  TektonConfig "config": updated validation is too restrictive: [].spec.trigger.disabled: Required value
  ```
  After patching them one by one it keeps hitting tektonresults / tektontriggers / tektonchains … — a systemic problem. Both the OLM auto-upgrade (channel switch) and manual uninstall+install paths get stuck.

### 2.2 Root cause (confirmed against the v0.80.0 release.yaml schema)
The following `spec` fields are marked `required` in the v0.80.0 CRDs while the older stored CRs lack them (extracted from the actual schema):

- **TektonConfig nested component blocks** (`spec.<component>.required`):
  - `trigger` → [disabled, options]; `chain` → [disabled, options]
  - `result` → [disabled, is_external_db, options]
  - `pipeline` → [options]; `hub` → [options]; `multiclusterProxyAAE` → [options]
  - `pruner` → [disabled]; `tektonpruner` → [disabled, global-config, options]
  - `scheduler` → [config.yaml, disabled, multi-cluster-disabled, multi-cluster-role, options]
  - `platforms.{kubernetes,openshift}.pipelinesAsCode` → [options]
- **operand CRD top level** (`spec.required`):
  - tektonpipelines/tektonhubs/tektonmulticlusterproxyaaes/manualapprovalgates → [options]
  - tektontriggers/tektonchains → [disabled, options]
  - tektonresults → [disabled, is_external_db, options]
  - tektonpruners → [disabled, global-config, options]
  - tektonschedulers → [config.yaml, disabled, multi-cluster-disabled, multi-cluster-role, options]

> Note: deeper nested `required` such as `performance.disable-ha`, `controllerEnvs[].name`, `valueFrom.*.key` are validated only **when the owning sub-object is present**; **unless** an older CR happens to set those optional sub-objects (e.g. `performance: {}` or a partial `controllerEnvs`), they are not upgrade blockers. The always-blocking paths are the "always present" ones: the operand CR `spec` top level, and the TektonConfig component blocks that necessarily exist under profile=all. A+'s recursive strip also covers these **conditional** paths, which incidentally closes the "old CR happened to carry an optional sub-object" hole — i.e. "strip a bit more, be safer".
>
> Coverage: the repo ships 14 `operator.tekton.dev` CRDs; among them `openshiftpipelinesascodes`/`syncerservices`/`tektoninstallersets` have no `spec.required` blocker but are still in the A+ strip target set (the script processes by group, naturally idempotent and side-effect-free).

Upstream history: after upstream replaced the hand-written CRDs with controller-gen-generated ones, the `options` (AdditionalOptions) Go field had no `+optional`/`omitempty`, so controller-gen emitted it into `spec.required`. Two upstream commits then fixed it:
- 6ae9dae4b "fix: options field should be optional in all components" https://github.com/tektoncd/operator/commit/6ae9dae4b — added `+optional` to `options` and regenerated `config/base/generated-crds/`, but did not resync the release `300-*_crd.yaml`.
- f0f903c80 "Cleanup manual CRDs and use generated CRDs in kustomize" https://github.com/tektoncd/operator/commit/f0f903c80 — regenerated the release CRDs too.

As of v0.80.0 (tagged 2026-06-24) **neither is in the published release.yaml**, so our downloaded artifact still marks `options` required; and `disabled`/`is_external_db` etc. are still required upstream to this day (that fix touched only `options`).

### 2.3 Relationship with DEVOPS-44427 (existing overlay fix)
- 44427 blocked only one CRD, ManualApprovalGate, and could be worked around with a direct `kubectl patch` of `options`. Its existing overlay fix already uses JSON6902 in `config/operator/kustomization.yaml` to drop `options` from the **top-level** `spec.required` of each operand CRD, but **deliberately keeps** `disabled`/`is_external_db` etc. (assumption: those fields are always serialized by struct-created CRs, so old CRs already satisfy them). That fix was validated on the 4.10 (operand v0.76.0) → 4.13 path.
- **This issue falsifies that assumption**: upgrading from the older 4.0.17 (v0.74.1) baseline, the stored CRs lack even `disabled` (the first error is exactly `spec.trigger.disabled`). And the existing overlay fix **does not touch** the TektonConfig **nested component block** `required` at all. So it is insufficient for 4.0.x → 4.13.
- This issue is also more severe: by default it **cannot be worked around by a direct patch** — ① patching the CR to add the field is denied by the 4.0.17 mutating webhook (unknown field); ② deleting the webhook and patching then loses the field, because the running 4.0.17 operator reconciles a typed struct and overwrites it; ③ patching the CRD to add preserve-unknown is rejected by the apiserver.

### 2.4 Why it is upgrade-specific (and why it slipped through testing)
A freshly installed CR is generated by the 4.13 operator with all fields present, so it never hits this; only "upgrade with historical data" triggers it. The current e2e only does fresh install (at deepest 4.10 → 4.13) and has never exercised a 4.0.x → 4.13 oldest-baseline upgrade → missed.

---

## 3. Goals / Non-Goals

### Goals
- G1: The OLM upgrade from 4.0.x (and any older baseline missing these fields) → 4.13 is no longer blocked by `required`; the InstallPlan reaches `Complete`.
- G2: **Zero side effects** of the fix on fresh install, the running operator, and the existing 4.10 → 4.13 upgrade path.
- G3: **Regression/recurrence prevention** — the next time upstream tightens `required` there is no field-by-field whack-a-mole; CI holds the line.
- G4: **Forward compatibility** — our published upgrade chain (upgrade to the transitional version, then to a future version we ship) is no longer blocked by `required`. This guarantee comes **primarily from "keeping the A+ strip as a permanent build step"** (uniform across all CRDs, independent of runtime behavior); the transitional version's data self-heal is only a **partial** bonus (holds for TektonConfig and most operands, not for MAG — see §5.4).

### Non-Goals
- NG1: Not fixing "post-upgrade manual configuration" items (MAG/pruner operand not auto-created, the `enable-pac-repository` switch, pointing the hub resolver at the air-gapped shim, changing ingress `ingressClassName` cpaas-system → global-alb2) — the owner has confirmed these are **expected behavior**, out of scope for this spec.
- NG2: Not changing upstream Go structs / not changing operator business logic in this repo (the upstream `+optional` convergence is Alternative B in §7, driven separately long-term).
- NG3: Not introducing a runtime webhook / migration Job to rewrite existing CRs (Alternatives C/D in §7, rejected).

---

## 4. Proposal: A+ generic normalization

On top of the operator overlay's CRD source (`config/operator/base/release.yaml`, downloaded from the upstream release), add one **deterministic normalization** step: for every CRD whose `spec.group == operator.tekton.dev`, recursively delete **every `required` array** under the `openAPIV3Schema.properties.spec` subtree (across all `versions`); do not touch `metadata`/`status`/top-level CRD structure/printer columns/`versions` themselves.

Why A+ rather than "field-by-field JSON6902":
- kustomize has no good wildcard delete for "recursively remove all `required`"; a long JSON6902 list is both verbose and misses conditional paths;
- these are operator-managed operand CRs whose `spec` is all configuration knobs, older CRs always lag, so `required` validation is worthless to us and only blocks upgrades;
- one-and-done: the next upgrade needs no field re-audit (G3).

Cost (stated honestly): it also removes `required` validation on nested structures (`controllerEnvs[].name`, `valueFrom.*.key`, `performance.disable-ha`, etc.), loosening admission — a malformed user-authored CR may be admitted and only surface at reconcile time. For operator-managed operand CRs this validation has little value, so it is acceptable.

---

## 5. Design Details

### 5.1 Normalization script (validated on a temporary copy)
Add `hack/strip-crd-spec-required.sh` (idempotent), built on the repo's existing `yq` v4:

```bash
yq eval -i '
  ( select(.kind == "CustomResourceDefinition"
           and .spec.group == "operator.tekton.dev").spec.versions[]
    | select(.schema.openAPIV3Schema.properties.spec != null)
      .schema.openAPIV3Schema.properties.spec )
  |= del(.. | select(has("required")).required)
' "$FILE"
```

Key points:
- `select(... .properties.spec != null)` is an **existence guard**: CRDs without `properties.spec` (inline/preserve-unknown, e.g. openshiftpipelinesascodes) are not materialized into `spec: null` (a pitfall the first draft of the expression hit, now fixed).
- `del(.. | select(has("required")).required)` recursively deletes all `required` starting from the `spec` node (both `spec` top level and every nested level).
- **Intentionally** limited to deleting any-level `required` inside the `properties.spec` subtree: even if some future field path is named `spec.status` (at the schema level) it is in scope; `status`/`metadata` schema, printer columns, top-level CRD structure, and the `versions` entries themselves are untouched. The `required` inside each CRD's `status` schema was verified to remain intact.

**Verified (temporary copy, repo untouched)**:
- After strip, the `required` count under the `spec` subtree of every `operator.tekton.dev` CRD is **0**.
- The diff vs the original only removes the `required:` arrays and their item lines; everything else is **byte-identical** (yq v4 preserves formatting), not a full reflow.
- Document count unchanged (all 14 operator.tekton.dev CRDs retained); line count only 5341 → 5235.

### 5.2 Where it is applied and the committed form
- Treat `release.yaml` as an "upstream download → then normalized" source: run the script against `config/operator/base/release.yaml` and **commit the normalized result** (so this fix takes effect immediately).
- Update the top comment of `config/operator/kustomization.yaml`: from "verbatim" to "verbatim, then normalized by `hack/strip-crd-spec-required.sh` (DEVOPS-44435)".

### 5.3 Remove the now-redundant existing overlay patches
- Once A+ lands, the existing overlay's JSON6902 patches (op:remove / op:replace) that target the operand top-level `spec.required` all become **no-ops**; delete them to avoid masking future upstream `required` changes.
- **Keep** the existing overlay's two `preserve-unknown-*options*.yaml` patches — they solve a **different** problem (`options.ingress` being pruned by the strict schema), unrelated to `required`.

### 5.4 Forward compatibility: primarily via the "permanent build-step strip", self-heal is only a partial bonus (confirmed against source)

The question the owner raised: after upgrading to the transitional version, will a later upgrade to a "still-`required` community version" be blocked again? The answer has two layers, and **you must not bet on self-heal**.

#### (1) Primary guarantee = Safeguard A: the permanent build-step strip (independent of self-heal, strongest)
A+ runs as a **permanent build step** on every `release.yaml` refresh → **every version we ship has CRDs without `required`** → our own upgrade chain (4.0.x → 4.13 → any future version we ship) is **never blocked by `required`**, regardless of whether upstream still keeps `required` (we strip after downloading the community release anyway). This is the **primary guarantee** of forward compatibility: stable and independent of runtime behavior.

#### (2) Bonus = self-heal: only **partial**, cannot be relied on alone
When the transitional operator reconciles, it rewrites the missing fields back for **some** CRs (because these fields have **no omitempty** in the Go structs — which is exactly why controller-gen marked them required; `tektonchain_types.go Disabled bool json:"disabled"`, `Options AdditionalOptions json:"options"`, `tektonresult_types.go IsExternalDB bool json:"is_external_db"`; note: `TektonConfigSpec`'s `Trigger/Chain/... ,omitempty` are struct values, and Go's omitempty has no effect on struct values, so they still serialize as `{disabled:false, options:{}}`). But **which CRs are actually rewritten** depends on whether each reconciler triggers a full Update. Verified findings:

- ✅ **TektonConfig rewrites itself**: `shared/tektonconfig/tektonconfig.go markUpgrade()` (called early in `ReconcileKind`), when the `ReleaseVersionKey` label differs from the new version (always the case on upgrade), calls `TektonConfigs().Update(tc)` (**not** UpdateStatus, around `:450`) → full rewrite, missing fields filled with zero values.
- ✅ **Operands that compare the version label rewrite**: TektonTrigger/TektonResult/TektonChain/TektonPipeline etc., `shared/tektonconfig/trigger/trigger.go UpdateTrigger` (and its structural siblings), on a `ReleaseVersionKey` label change, call `clients.Update(old)` → full rewrite → filled.
- ❌ **ManualApprovalGate is not rewritten**: its reconciler (`kubernetes/manualapprovalgate/reconcile.go`) only updates status/installerset, **not the CR spec**; and MAG uses a minimal manifest to begin with (`spec` has only targetNamespace — the DEVOPS-44427 root cause), so `options` is never persisted.

**Conclusion**: self-heal covers TektonConfig + most TektonConfig-managed operands, but **not MAG**. Therefore:
- Forward compatibility relies **primarily on Safeguard A (the permanent strip)**, which is uniform across all CRDs and independent of self-heal;
- If we ever want to **retire** the strip (upstream fully fixed, or a customer bypasses our overlay and upgrades straight to a pure-community `required` version), we **must not assume the data has self-healed** — MAG's stored CR would still block; at that point an **explicit data migration** is required (a one-shot pre-upgrade InstallerSet/job that force-rewrites that CR, or add a full struct Update to its reconciler) before the strip can be safely retired. This is captured as a precondition of Alternative B in §7 and AC-8 in §11.
- The only new blocking source: a community version **adds a new `required` field the transitional version does not yet know about** — a property of any N→N+1 upgrade, caught by the oldest-baseline upgrade e2e in §6.

### 5.5 CI guard (recurrence prevention)
Add `hack/verify-crd-spec-required.sh`: assert against `config/operator/base/release.yaml` (and if needed the `kustomize build config/operator` render) that the `required` count under the `spec` subtree of every `operator.tekton.dev` CRD is 0; non-zero → fail. Wire it into `make verify` / CI, so any future `release.yaml` refresh that forgets the normalization goes red and forces a re-run (hedging the "no automated download target, easy to forget" risk).

### 5.6 Upgrade workflow documentation
Record in the operator upgrade handbook / `.tekton/patches` README: after every `release.yaml` refresh you must run `make strip-operator-crd-required` (or the equivalent script), with the §5.5 verification as the backstop.

---

## 6. Test Plan

- T1 (regression, primary): add an **"upgrade from the oldest supported baseline (4.0.x) to the current version"** product e2e lane: deploy 4.0.x profile=all → upgrade to a build containing this fix (**via the final rendered bundle / real InstallPlan path**, not just CRD schema assertions) → assert InstallPlan Complete, CSV Succeeded, TektonConfig and each operand Ready, and an existing Pipeline still runs successfully after the upgrade. Directly hedges the missed-test root cause and answers the retrospective. (maps to AC-1)
- T2 (self-heal verification, tiered): after upgrade dump the stored CRs and assert — TektonConfig and the version-label-comparing operands (Trigger/Result/Chain/Pipeline) `disabled`/`is_external_db` etc. are **filled** (AC-2a); and **explicitly assert MAG's `options` may still be absent** (AC-2b known limitation), to avoid the illusion of full self-heal.
- T3 (script/verify unit): `hack/verify-crd-spec-required.sh` returns non-0 for a "contains required" sample and 0 for a "stripped" sample; the script is idempotent (running twice yields an empty diff); add a negative case — after strip, a malformed user CR is admitted and fails at reconcile time (maps to R1).
- T4 (no side effects): the existing fresh-install e2e and 4.10 → 4.13 upgrade e2e stay green.

---

## 7. Alternatives considered

- **A (field-by-field JSON6902)**: hand-list the removals for the tektonconfigs nested blocks + operand top level in kustomization.yaml. Small diff, matches the existing overlay style, but **whack-a-mole**, misses conditional paths, needs a field re-audit every upgrade. Superseded by A+ (kept as the "minimal viable" contrast).
- **B (push `+optional` upstream)**: also add `+optional` to `disabled`/`is_external_db` etc. and wait for a community release. Cleanest but slow, off the productization critical path; a **long-term convergence**. **Precondition for retiring the overlay** (per §5.4): cannot rely on self-heal alone — MAG's stored CR does not self-heal, so before retiring the strip an **explicit data migration** is mandatory (a one-shot pre-upgrade InstallerSet/job to force-rewrite that CR, or add a full struct Update to its reconciler), otherwise retiring the strip lets MAG block again.
- **C (defaulting/conversion webhook)**: **rejected**. OLM compares existing CRs against the new schema at CRD-apply time; the webhook never runs, so it does not address the root cause.
- **D (pre-upgrade migration Job to add fields)**: **rejected**. It requires stopping the 4.0.x operator + deleting its webhooks to add the fields without them being overwritten — exactly the heavy manual workaround from the ticket, high risk, not a product solution.

---

## 8. Risks & Mitigations

- R1: A+ removes nested `required` validation → looser admission; a malformed user-authored CR may be admitted and only surface at reconcile time. Mitigation: low value for operator-managed CRs; if needed, re-add validation for specific user-editable fields later; add a negative test making explicit that "a malformed user CR is now admitted and fails at reconcile" (T3 extension).
- R5 (forward-compat blind spot): MAG's stored CR does not self-heal (§5.4). Mitigation: forward compatibility relies primarily on Safeguard A (the permanent strip), not on self-heal; retiring the strip requires an explicit data migration first (Alternative B precondition + AC-8).
- R2: `release.yaml` is normalized in place, deviating from the "upstream verbatim" invariant; easy to forget the re-run on a future refresh. Mitigation: §5.5 CI red-light backstop + §5.6 handbook record.
- R3: A future community version adds an unknown `required` field, blocking again. Mitigation: the §6 T1 oldest-baseline upgrade e2e as a standing gate catches it immediately.
- R4: self-heal depends on the transitional version reconciling ≥1 time. Mitigation: the operator reconciles on startup and markUpgrade Updates early — reliable; you only need to avoid jumping to the next version within seconds while the operator is not yet up (does not happen in practice).

---

## 9. Rollback
Normalization is a build-time relaxation of the CRD schema (only deletes `required`, does not change fields/types); purely backward compatible. To roll back, restore `release.yaml` and kustomization.yaml and drop the script and verification; it does not affect already-self-healed stored data.

---

## 10. Retrospective (answering the two bot questions)
- Why it was not caught: the existing e2e only covers fresh install (at deepest 4.10 → 4.13), with no "oldest-baseline upgrade" path; the defect is upgrade-specific and the always-green fresh install masked it.
- Improvements: ① (this spec's fix) A+ generic normalization, so `required` never blocks upgrades at the root; ② a standing CI guard against recurrence; ③ add an "upgrade from the oldest supported baseline" e2e lane, bringing the upgrade path into regression.

---

## 11. Acceptance criteria (EARS)
- AC-1 (operator) WHEN a 4.0.x (operand v0.74.1) profile=all environment is upgraded via OLM to a 4.13 build containing this fix (**via the final rendered bundle / real InstallPlan path**, not just CRD schema assertions) THE OLM SHALL bring the InstallPlan to `Complete` and the CSV to `Succeeded`, with no `updated validation is too restrictive: ... Required value`.
- AC-2a (operator) WHEN the operator completes its first reconcile after the upgrade THE operator SHALL persist (self-heal) the missing fields on the stored **TektonConfig** (`spec.trigger.disabled`/`spec.result.is_external_db` etc.) and on the **version-label-comparing operands** (TektonTrigger/TektonResult/TektonChain/TektonPipeline, `spec.disabled` etc.).
- AC-2b (operator) `[known limitation]` WHILE upgrading to a transitional build containing this fix THE **ManualApprovalGate** stored CR SHALL **not be guaranteed** to self-heal its `options` (the MAG reconciler does not rewrite the CR spec) — this is a **documented known limitation**, does not affect this upgrade (its CRD is already A+-stripped and has no `required`), and only constrains "retire the strip" (Alternative B in §7).
- AC-3 (build) WHEN the normalization script runs against `config/operator/base/release.yaml` THE script SHALL make the `required` count under the `openAPIV3Schema.properties.spec` subtree of every `operator.tekton.dev` CRD equal to 0, and **only delete `required` within the spec subtree** — not altering the `status` schema, `metadata`, printer columns, top-level CRD structure, nor adding/removing any `versions` entry.
- AC-4 (build) IF a `release.yaml` refresh is not normalized (residual `required` exists) THEN `make verify` / CI SHALL fail.
- AC-5 (build) WHEN the normalization script runs twice against the same file THE second run SHALL produce a zero diff (idempotent).
- AC-6 (api) WHILE a Pipeline is created and runs successfully before the upgrade WHEN the upgrade completes THE Pipeline SHALL retain a consistent `spec` and run successfully again (upgrade does not break existing assets).
- AC-7 (build) WHEN A+ lands THE kustomization.yaml SHALL no longer keep the existing overlay's now-no-op operand `spec.required` JSON6902 patches, and SHALL **still keep** the `preserve-unknown` patches.
- AC-8 (operator) `[forward-compat boundary]` IF we ever **retire** the A+ strip and upgrade to a still-`required` community version THEN that path SHALL either first run an explicit data migration on the MAG stored CR and then validate, or **explicitly declare it out-of-scope pending migration** in the docs; it SHALL NOT assume "the data has already self-healed".

---

## 12. Traceability (evidence and files to change)
- Evidence (source): `config/operator/base/release.yaml` (v0.80.0 CRD schema, the `required` lists in this spec are extracted from it); `upstream/pkg/apis/operator/v1alpha1/*_types.go` (json tags without omitempty); `upstream/pkg/reconciler/shared/tektonconfig/tektonconfig.go` (markUpgrade Update); `upstream/pkg/reconciler/shared/tektonconfig/trigger/trigger.go` (UpdateTrigger).
- Evidence (issue): DEVOPS-44435, DEVOPS-44427 (existing overlay fix).
- Files to change (planned): add `hack/strip-crd-spec-required.sh`, `hack/verify-crd-spec-required.sh`; the normalized `config/operator/base/release.yaml`; `config/operator/kustomization.yaml` (drop redundant `required` patches + update comment); `Makefile` (strip / verify targets); the upgrade handbook; add the oldest-baseline upgrade e2e (`testing/**`).
