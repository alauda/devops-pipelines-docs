---
status: proposed
title: Configurable Catalog Task Images via Public ConfigMap
creation-date: "2025-11-27"
category: task
authors:
  - "@zichenyu"
---

# TEP-0005: Configurable Catalog Task Images via Public ConfigMap

## Summary

**Goal**: manage multi-version catalog images via `ConfigMaps` so users see both new and old image options across upgrades.

Three alternative approaches are proposed:

1. **Custom controller fan-out**: per-task, per-version `ConfigMaps` live in `tekton-pipelines` with two fields (`name`, `image`) and Task/version labels; a controller in `tektoncd-enhancement` copies them non-destructively to `kube-public`, keeping old entries visible.
2. **Operator preserve policy**: Add the ability for the Tekton Operator to retain resources from older versions. Mark `ConfigMaps` (or other resources) with `operator.tekton.dev/resource-policy: keep`; the tektoncd-operator detaches them from TektonInstallerSet lifecycle (no ownerRefs, no deletion) so existing versions remain when InstallerSets are replaced during upgrades.
3. **Advanced import and mutation**: Support delete, patch-only, and mutation strategies—potentially packaged as an image plus initContainer in `tektoncd-enhancement`—to manage legacy `ConfigMaps` without coupling business-specific logic into tektoncd-operator.

## Motivation

Tekton catalog users need dropdowns for common Task images (kubectl, helm) and require image tag stability across upgrades. The [v3 UX](https://confluence.alauda.cn/pages/viewpage.action?pageId=227247112) consumed `ConfigMaps` from `kube-public`; retaining that contract minimizes migration friction.

### Goals

- Provide dropdown options for common Task images (kubectl, helm, run-script) via `ConfigMaps` consumed by dynamic forms.
- Offer multiple versioned images for language Tasks (Go, Python, etc.) with stable defaults and explicit version labels.
- Keep default image parameters populated to avoid breaking existing TaskRuns that did not override `image`.
- Standardize catalog image tags to minor-only tags (for example, `v7.0`) and publish a `latest` alias for the newest minor release.
- Maintain user ability to input arbitrary image URLs.
- Ensure older image options remain visible after upgrades while introducing new versions.

### Non-Goals

- Introducing new public APIs or CRDs for image discovery beyond the `ConfigMap` reconciled by the controller.

### Use Cases

- UI users pick `kubectl` or `helm` images for a generic run-script Task without editing YAML manually.
- Language Task consumers choose Go 1.24 versus Go 1.25, or Go 1.25 with an explicit `Latest (Go 1.25)` label, from a dropdown.
- UI can surface old and new versions simultaneously so ongoing TaskRuns can reference prior images while new ones roll out.

### Requirements

- Image option lists should be published in `kube-public` so the UI can read them cluster-wide.
- Default image parameters in catalog Tasks must remain non-empty to avoid breaking existing TaskRuns.
- Image tags must be available for all referenced Task versions; latest tags must remain aligned with the newest supported minor.
- Users must be able to override the dropdown by entering a full image reference manually.
- Older `ConfigMap` entries must remain available alongside newer ones after upgrades.

## Proposal

### Proposal A: ConfigMap fan-out and retention (custom controller)

- Ship per-task, per-version `ConfigMaps` in `tekton-pipelines`.
- Add a controller in `tektoncd-enhancement` that watches the source `ConfigMaps` which have specified labels and applies them into `kube-public`, preserving existing `ConfigMaps` while appending/updating new ones (non-destructive).

### Proposal B: Preserve policy for unmanaged resources (tektoncd-operator)

- Resources annotated with `operator.tekton.dev/resource-policy: keep` are treated as out-of-lifecycle for TektonInstallerSets.
- The operator skips injecting TektonInstallerSet ownerRefs for these resources.
- During InstallerSet finalization or DeleteCollection cleanup, keep-annotated resources are skipped so they remain in the cluster after upgrades.

### Proposal C: Import, patch, and mutate via tektoncd-enhancement

- Introduce strategies beyond create/update: `patch-only` (patch existing objects only), `delete` (remove objects that exist), and `mutation` (rewrite manifests based on cluster info such as registry prefixes).
- Reuse the v3 import/mutation pipeline in `tektoncd-enhancement` (see [cmd/controller/main.go#L289-304](https://gitlab-ce.alauda.cn/devops/katanomi/-/blob/release-3.20/cmd/controller/main.go#L289-304) and [pkg/taskimport/importer.go#L122](https://gitlab-ce.alauda.cn/devops/katanomi/-/blob/314a69a2cb097aab93f27787bf6d183b53e6c499/pkg/taskimport/importer.go#L122)) to minimize migration effort.
- Package `ConfigMaps` into an image and use an initContainer in `tektoncd-enhancement` to import them locally, decoupling catalog data from controller code.

### Notes and Caveats

- The `ConfigMap` is readable by most of the users; sensitive data must not be stored in it.
- If the `ConfigMap` is missing, the UI still shows a free-text `image` field; only convenience dropdowns are affected.
- Runtime-specific defaults remain pinned to the previous minor during an upgrade until new Task versions are released without defaults.
- Keep semantics apply only when the annotation is present; other resources remain lifecycle-managed.

## Design Details

### Proposal A: ConfigMap fan-out

#### Controller Responsibilities

1. `TektonInstallerSet` will place all `ConfigMaps` shipped with the current version into the `tekton-pipelines` namespace.
2. The controller in `tektoncd-enhancement` needs to watch `ConfigMaps` in `tekton-pipelines` that have a label like `enhancement.tekton.dev/fan-out: kube-public`, and distribute them to the specified namespaces (for example, `kube-public`).
3. If the target namespace already has the `ConfigMap`, the controller updates it; otherwise, it creates the `ConfigMap`.
4. The controller will not delete `ConfigMaps` in the target namespaces.
5. The main purpose of this is that for `ConfigMaps` managed by `TektonInstallerSet`, if a newer version no longer includes a given `ConfigMap`, that `ConfigMap` will be removed from the cluster during upgrade (because it has a `TektonInstallerSet` ownerReference).
6. Alternative approach: handle these `ConfigMaps` using bootstrap logic. When `TektonInstallerSet` installs resources, it imports static resources before importing the Deployment, so we can also consider running this only during the initialization phase. However, this would require putting the `ConfigMap` and `tektoncd-enhancement` into the same `TektonInstallerSet` (`Tekton Pipeline`), which would make the mechanism less generic; if other components have similar needs in the future, they would not be able to directly reuse this capability.

   ```yaml
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: tekton-task-go-1-25
     namespace: tekton-pipelines
     labels:
       # fan-out to kube-public
       enhancement.tekton.dev/fan-out: kube-public
       catalog.tekton.dev/source: system
       catalog.tekton.dev/tool-image-golang: 1.25
       catalog.tekton.dev/tool-image-run-script: go-1.25
   data:
     name: "Go 1.25"
     image: "registry.example.com/tekton/golang:1.25"
   ```

### Proposal B: Preserve policy for unmanaged resources

1. Helm has a `resource-policy: keep` annotation that can take a resource out of a release's lifecycle. A similar feature would satisfy we need.
2. Resources with `operator.tekton.dev/resource-policy: keep` skip `ownerRef injection` for TektonInstallerSets. So that they remain in the cluster after upgrades.
3. As versions evolve, we may remove some outdated `ConfigMaps` from `kodata` and start maintaining other `ConfigMaps` instead. On one hand, we want users who upgrade from older versions to still see those legacy `ConfigMaps` so things remain compatible; on the other hand, we don't want newly installed environments to see those `ConfigMaps` anymore, because they're already obsolete.
4. The amount of change won't be very large. In the `TektonInstallerSet` reconcile logic, the `ownerRef injection` has already been extracted into a separate method, so we only need to add some annotation-based checks in that method.
5. My Issue link: [Preserve legacy TektonInstallerSet resources when removed from manifests](https://github.com/tektoncd/operator/issues/3017)

   ```yaml
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: tekton-task-go-1-25
     namespace: tekton-pipelines
     annotations:
       # keep annotation that can take a resource out of TektonInstallerSet lifecycle 
       operator.tekton.dev/resource-policy: keep
     labels:
       catalog.tekton.dev/source: system
       catalog.tekton.dev/tool-image-golang: 1.25
       catalog.tekton.dev/tool-image-run-script: go-1.25
   data:
     name: "Go 1.25"
     image: "registry.example.com/tekton/golang:1.25"
   ```

### Proposal C: Import, patch, and mutate (tektoncd-enhancement)

1. Extend beyond create/update with three strategies:
   - `patch-only`: When an object already exists, apply a partial patch; if absent, do nothing.
   - `delete`: When an object exists, delete it.
   - `mutation`: Rewrite manifests before import (for example, derive registry prefixes from the current cluster and replace image URLs).
2. Keep `patch-only` and `mutation` logic in `tektoncd-enhancement` because they are business-specific and should not be coupled into tektoncd-operator.
3. If needed, port the v3 import/mutation pipeline from `tektoncd-enhancement` (see [cmd/controller/main.go#L289-304](https://gitlab-ce.alauda.cn/devops/katanomi/-/blob/release-3.20/cmd/controller/main.go#L289-304) and [pkg/taskimport/importer.go#L122](https://gitlab-ce.alauda.cn/devops/katanomi/-/blob/314a69a2cb097aab93f27787bf6d183b53e6c499/pkg/taskimport/importer.go#L122)) to minimize migration effort.
4. Package catalog `ConfigMaps` into an image and run an initContainer in `tektoncd-enhancement` to import them locally, avoiding direct coupling between catalog data and controller code.

### Approach Comparison

#### Proposal A (tektoncd-enhancement controller-based)

- **Pros**:
  - Implemented as a standalone controller, so there is no need to modify the tektoncd-operator source code, avoiding conflicts during future upgrades.
  - The mechanism is fairly generic; if we have similar requirements in the future, we can reuse this label for fan-out.
- **Cons**:
  - There is an ongoing cost to maintaining an additional controller.
  - The resources that the catalog cares about cannot be maintained directly in `tektoncd-enhancement`, resulting in redundant `ConfigMaps` in both tekton-pipelines and kube-public. (There is also a way to avoid creating redundant `ConfigMap` resources. You can consider packaging the `ConfigMap` into an image, then configuring an initContainer for `tektoncd-enhancement` to directly import the `ConfigMap` into the `tektoncd-enhancement` directory.)

#### Proposal B (tektoncd-operator preserve policy)

- **Pros**:
  - The semantics of the annotation are clear; this mechanism can be applied to any resource, and together with the `operator.tekton.dev/preserve-namespace: "true"` annotation it allows resources to be installed directly into the specified namespace.
  - Requires relatively little development effort and does not consume additional resources.
- **Cons**:
  - It introduces changes to tektoncd-operator, so future upgrades may encounter conflicts.
  - Troubleshooting is relatively more difficult; if behavior does not match expectations, you need to inspect tektoncd-operator logs and code directly.

#### Proposal C (tektoncd-enhancement import/mutation pipeline)

- **Pros**:
  - Covers delete, patch-only, and mutation scenarios without coupling business logic into tektoncd-operator.
  - Reuses the v3 pipeline and can be packaged as an initContainer-driven import, keeping catalog data and controller code loosely coupled.
- **Cons**:
  - Adds complexity to `tektoncd-enhancement` and requires extra testing for the strategy matrix.
  - More configuration/annotations may increase operational overhead for users.

### Conclusion

Choose `Proposal B`. 

In addition, v3 previously supported some mutator logic for image prefix replacement. 
In v4, we currently rely on dynamic replacement before Pod creation, which introduces some performance overhead but is sufficient for image usage. 
At this stage, we will first implement the resource import capability according to Proposal B, and analyze and design dynamic replacement and deletion capabilities later if needed.

### Future extensions

Future work that needs `delete`, `patch-only`, or `mutation` flows can be added by extending along Proposal C (import, patch, and mutate via tektoncd-enhancement); see that section for concrete strategies, annotations, and references to the v3 pipeline.

For the `delete` strategy, consider a new annotation such as `operator.tekton.dev/resource-policy: delete` that removes matching resources if present. Its purpose would be to check whether the resource exists in the cluster and, if it does, delete it.

### Common Logic

#### ConfigMap Schema

Each `ConfigMap` holds exactly one image option for a specific Task and Task version. Two data fields are present: `name` (display label) and `image` (full image reference). 
Labels identify the target Task and version so the controller/UI can match them.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: tekton-task-go-1-25
  namespace: kube-public
  labels:
    catalog.tekton.dev/source: system
    catalog.tekton.dev/tool-image-golang: 1.25
    catalog.tekton.dev/tool-image-run-script: go-1.25
data:
  name: "Go 1.25"
  image: "registry.example.com/tekton/golang:1.25"
```

Field meanings:
- `name`: human-friendly option text shown in the dropdown.
- `image`: full image reference.

Required labels (example keys shown above):
- `catalog.tekton.dev/source`: identifies the source of the `ConfigMap`.
- `catalog.tekton.dev/tool-image-<tool>`: identifies the tool image for the Task.
- `catalog.tekton.dev/tool-image-run-script`: identifies the tool image for `run-script` Task.

#### Catalog Task Changes

- Maintain the existing `image` parameter default value for each Task; do not clear defaults to avoid breaking current TaskRuns.
- Update catalog images to use minor-only tags (for example, `v7.0`) and publish a `latest` alias for the newest minor release.
- For language Tasks, publish one `ConfigMap` per version with `name`/`image` data and labels; defaults stay on the current minor (for example, Python 3.13) until a new Task minor is added.
- When introducing a new runtime minor (for example, Python 3.14), keep the older Task minor default pointing to the previous image (3.13) and add a new Task minor with no default image to force explicit selection; add the corresponding per-version `ConfigMap` for discovery.

  ```yaml
  global:
    images:
      python-3.13:
        repository: devops/tektoncd/hub/python
        digest: sha256:c603e490c552823f9361cbd7fde2f2b374ec66f2b1175b3871ec9dc474c36bff
        tag: v3.13
      python-latest:
        repository: devops/tektoncd/hub/python
        digest: sha256:c603e490c552823f9361cbd7fde2f2b374ec66f2b1175b3871ec9dc474c36bff
        tag: latest
  ```

#### UI Integration

- Tasks already declare dynamic form metadata for `image` parameters; the UI lists `ConfigMaps` in `kube-public` filtered by Task/version labels.
- Dropdown rendering derives the option label from `data.name` and the image from `data.image`.
- Users can always override by typing a full image reference; dropdown is a convenience, not a constraint.
- If the `ConfigMaps` are unreachable, the UI falls back to a text field without options.

#### Compatibility and Tagging

- Tag format shifts from `v7.0.2-v4.3.0-<hash>` to `v7.0` to ensure image availability across Task patch bumps.
- A `latest` tag is maintained to align the UI “Latest (…)” option with the newest supported minor.
- Existing TaskRuns that relied on implicit defaults keep working because defaults remain populated with valid minor tags.
- Per-version `ConfigMaps` make it explicit which image belongs to which Task/version without multi-entry payloads.

## Design Evaluation

### Reusability

- Keeps runtime selection as an author-time concern while letting operators curate image lists centrally.

### Simplicity

- UI change is limited to reading a `ConfigMap`; Task definitions keep the same parameters.
- Defaulted images avoid surprising failures for existing TaskRuns.
- Keep policy is opt-in via a single annotation.

### Flexibility

- Users can bypass the curated list by entering any image.
- New runtime versions can be added by updating the `ConfigMap` data without changing the UI code.
- Operators can choose which resources to preserve by applying the keep annotation.

### Conformance

- No Tekton API changes; only Task parameter defaults and image tags are updated.
- Uses standard Kubernetes `ConfigMaps` in a public namespace, consistent with prior versions.

### User Experience

- Dropdown labels match v3 wording (“Python 3.13” and “Latest (Python 3.13)”), reducing migration friction.
- Manual entry remains available for power users and air-gapped registries.
- Operators gain a clear, declarative way to retain specific resources across upgrades.

### Performance

- UI fetch is a single `ConfigMap` read; no additional API calls per TaskRun.
- Keep policy only changes ownerRef handling; no extra reconciler loops are added.

### Risks and Mitigations

- **Risk:** `ConfigMap` missing or deleted. **Mitigation:** Controller recreates; UI falls back to text input.
- **Risk:** Namespace access issues in restricted clusters. **Mitigation:** Use `kube-public`; document required RBAC for read access. This assumes the Kubernetes default where all authenticated users have read-only access to that namespace; if a hardened cluster removes that default, operators must reintroduce equivalent read permissions.
- **Risk:** Forgetting the keep annotation on resources that must persist. **Mitigation:** Document the contract; audit manifests during upgrades.

### Drawbacks

- Keep policy relies on annotations and operator logic; accidental omission can still delete resources.
