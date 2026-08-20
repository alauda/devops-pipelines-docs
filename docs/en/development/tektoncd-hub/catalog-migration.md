---
weight: 20
title: Legacy Custom Catalog Migration
---

# Legacy Tekton Hub Custom Catalog Migration

Starting from v4.14.0, the operator migrates legacy Tekton Hub custom catalog settings to ArtifactHub Shim before it removes the old Tekton Hub runtime. This document describes the implementation contract for developers and maintainers.

For the user-facing upgrade checks, see [Upgrade](../../upgrade/upgrade.mdx).

## Goals and Boundaries

The migration has the following goals:

- Preserve custom Task, Pipeline, and StepAction catalog references when the built-in Tekton Hub runtime is removed.
- Convert only configuration already stored in Kubernetes resources, so the migration works in air-gapped environments.
- Avoid overwriting existing ArtifactHub Shim repositories or user-managed Kubernetes resources.
- Normalize supported legacy SSH credentials without exposing or copying unrelated Secret data.

The migration does not fetch `TektonHub.spec.api.hubConfigUrl`, clone Git repositories, or verify that a Git endpoint is reachable. ArtifactHub Shim performs repository refresh and reports connectivity or credential errors after it discovers the generated configuration.

## Execution Flow

The same migration helper runs from two paths:

1. The TektonConfig pre-upgrade sequence migrates all existing `TektonHub` resources.
2. The Kubernetes `TektonHub` reconciler migrates the resource being reconciled immediately before cleaning up the removed Hub runtime.

Both callers propagate migration errors. The `TektonHub` reconciler does not start runtime cleanup when migration returns an error. This second entry point also protects installations where the legacy resource is reconciled independently of the main pre-upgrade sequence.

Each migration run performs these steps:

1. Collect the applicable `TektonHub` resources.
2. Resolve the ArtifactHub Shim namespace.
3. Scan existing ArtifactHub Shim repository configuration for name and alias conflicts.
4. Read and normalize a legacy SSH Secret when at least one catalog uses an SSH URL.
5. Convert valid, non-conflicting catalog entries into a deterministic `repository.yaml` document.
6. Create or safely update the operator-managed ConfigMap and Secret.

## Input Collection

For each `TektonHub`, the migration reads catalogs from these sources in order:

1. `TektonHub.spec.catalogs[]`.
2. The `CATALOGS` key in the `tekton-hub-api` ConfigMap in the Hub target namespace.

The rendered ConfigMap format accepts both the legacy lowercase keys, such as `sshurl` and `contextdir`, and their camel-case forms, `sshUrl` and `contextDir`. It can also supply `disabledPackages` rules that are available only in the rendered data.

Catalogs are deduplicated by normalized name, effective URL, revision, and context directory. The first matching entry keeps its clone fields, which gives the `TektonHub` specification precedence over an identical rendered ConfigMap entry, while `disabledPackages` rules from every duplicate are merged. Version lists for the same package are combined in first-seen order. An empty version list disables the whole package and takes precedence over version-specific rules.

The legacy `tekton-hub-api` ConfigMap can be removed after the first successful migration. To keep rendered-only disable rules across later reconciles, the migration also reads its existing managed repository ConfigMap when the `generated-by` annotation is correct and `generated-hash` still matches the current `repository.yaml`. Data from a user-managed or manually edited ConfigMap is never inherited. Invalid legacy `CATALOGS` YAML is logged and skipped without discarding valid catalogs from the custom resource.

The legacy `org`, `type`, and `provider` values are read for compatibility but are not required by ArtifactHub Shim and are not emitted.

## Destination Namespace and Resources

The migration extracts the ArtifactHub Shim namespace from `TektonConfig.spec.pipeline.hub-resolver-config.artifact-hub-api`. It accepts an ArtifactHub Shim service URL and uses the second DNS label as the namespace. If the value is absent or cannot be recognized, the migration uses `artifacthub-shim-system`.

The generated repository ConfigMap has the following contract:

| Field | Value |
| --- | --- |
| Name | `artifacthub-shim-legacy-tekton-hub-catalogs` |
| Namespace | Resolved ArtifactHub Shim namespace |
| Label | `artifacthub-shim.alauda.io/repository: "true"` |
| Data key | `repository.yaml` |

The optional generated SSH Secret is named `artifacthub-shim-legacy-tekton-hub-ssh-creds` in the same namespace.

## Catalog Conversion

One legacy catalog can produce up to three ArtifactHub Shim repository entries:

| Legacy catalog | Kind | Generated name | Generated path | Legacy alias |
| --- | --- | --- | --- | --- |
| `<catalog>` | `task` | `<catalog>` | `<contextDir>/task` | None |
| `<catalog>` | `pipeline` | `<catalog>-pipelines` | `<contextDir>/pipeline` | `<catalog>` |
| `<catalog>` | `stepaction` | `<catalog>-stepactions` | `<contextDir>/stepaction` | `<catalog>` |

An empty context directory produces the paths `task`, `pipeline`, and `stepaction`. Every generated entry sets `optional: true`, allowing a legacy repository to omit one or more resource-kind directories. Pipeline and StepAction aliases preserve kind-scoped resolver references that used the original catalog name.

Additional conversion rules are:

- `sshUrl` takes precedence over `url` when both are present.
- `sshUrl` accepts both `ssh://` URLs and native Git SCP-like `[user@]host:path` syntax; the selected value is emitted unchanged.
- An empty revision defaults to `main`.
- `disabledPackages` is copied to each generated kind entry.
- HTTP and HTTPS URLs containing inline user information are rejected; credentials must be stored in a Secret.
- A catalog without a name or usable URL is skipped with a warning.

Repositories are sorted by their first generated entry name before serialization so repeated reconciles produce stable data and hashes.

## SSH Credential Migration

SSH credential migration runs only when at least one effective catalog URL comes from `sshUrl`. Source Secret candidates are evaluated in this order:

1. A Secret referenced by the `operator.tekton.dev/legacy-git-credential-secret` annotation on the `TektonHub` resource.
2. A Secret referenced by the same annotation on the legacy `tekton-hub-api` ConfigMap.
3. The standard `tekton-hub-api-ssh-crds` Secret in the Hub target namespace.

An annotation can contain either a Secret name in the Hub namespace or an explicit `namespace/name` reference.

The generated Secret contains only these keys:

- `sshPrivateKey`, selected first from `sshPrivateKey` or `ssh-privatekey`, otherwise from exactly one of `id_rsa` and `id_ed25519`.
- `known_hosts`, copied from the legacy Secret.

If `known_hosts` is missing, no private key is present, or both legacy private-key candidates are present, the Secret is not generated. The catalog entry is still migrated without `credentialRef`, and ArtifactHub Shim reports the credential problem when it refreshes the source. HTTPS-only catalogs never trigger SSH Secret migration.

## Conflict Handling and Ownership

Before generating entries, the migration reserves the built-in `catalog`, `catalog-pipelines`, and `catalog-stepactions` repositories and scans all labeled ArtifactHub Shim repository ConfigMaps in the destination namespace.

A generated entry is skipped when:

- Its canonical repository name is already used.
- Its kind-scoped legacy alias conflicts with an existing canonical name.
- Its kind-scoped legacy alias is already registered by another repository.

Conflicts are handled per generated kind. For example, an existing Task repository can block the migrated Task entry while the Pipeline and StepAction entries from the same legacy catalog are still generated. An existing repository ConfigMap with invalid YAML is logged and excluded from the conflict index.

Generated resources carry these annotations:

- `operator.tekton.dev/generated-by` identifies the migration controller.
- `operator.tekton.dev/generated-hash` records a hash of the managed data.
- The generated Secret also records its source in `operator.tekton.dev/legacy-git-credential-secret`.

The operator updates a generated ConfigMap or Secret only when the `generated-by` value matches and the stored hash still matches the current data. A same-name user-managed resource or a generated resource edited after creation is preserved. When the desired managed data and metadata are already identical, the operator skips the Kubernetes Update call so repeated reconciles keep a stable `resourceVersion`. When no valid repository entries remain, the migration does not create, update, or delete the managed ConfigMap.

## Verification and Troubleshooting

Inspect the generated repository configuration without modifying it:

```bash
kubectl get configmap artifacthub-shim-legacy-tekton-hub-catalogs \
  -n artifacthub-shim-system \
  -o yaml
```

Use the namespace encoded in `artifact-hub-api` when ArtifactHub Shim is installed outside `artifacthub-shim-system`.

For SSH catalogs, verify that the normalized Secret exists without printing its data:

```bash
kubectl get secret artifacthub-shim-legacy-tekton-hub-ssh-creds \
  -n artifacthub-shim-system
```

When an expected entry is missing, review operator warnings for invalid legacy YAML or URLs, repository name and alias conflicts, invalid SSH Secret data, and preservation of user-managed resources. Then inspect ArtifactHub Shim repository events to diagnose Git refresh failures.

See [the release notes](../../overview/release_notes.mdx) for the v4.14.0 release contract and [Upgrade](../../upgrade/upgrade.mdx) for operational checks.
