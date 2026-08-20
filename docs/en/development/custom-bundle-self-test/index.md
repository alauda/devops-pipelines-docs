---
created: '2026-03-11'
updated: '2026-03-11'
weight: 35
---

# Build a Custom Bundle for Self-Testing

## Background

When you need to validate local `tektoncd-operator` changes quickly, rebuilding all component images is slow and unnecessary.

This guide shows how to:

1. update `.ko` manifests for your target registry,
2. build a custom operator image for testing,
3. trigger `to-build-bundle-image` with pinned artifact tags.

## Prerequisites

- Push permission for your image repository.
- Permission to trigger Pipelines as Code (PAC) in this repository.
- Local tools: `podman`, `git`, `yq`.

## Step 1. Prepare Branch and Image Tags

Use the same branch as the bundle build (for example `release-4.6`) and refresh `values.yaml` from Nexus:

```bash
git checkout release-4.6
make download-release-from-nexus
```

Read the frontend tag from `values.yaml`:

```bash
yq e '.global.images.pipeline-v2-frontend_ui.tag' values.yaml
```

Export the tags that will be used in `overwrite_artifacts`:

```bash
export TARGET_BRANCH="release-4.6"
export UI_TAG="$(yq e '.global.images.pipeline-v2-frontend_ui.tag' values.yaml)"
export COMMON_COMPONENT_TAG="<component-tag-from-release-pipeline>"
```

`COMMON_COMPONENT_TAG` is not read from `values.yaml`.
Get it from the corresponding `release-*` pipeline outputs (for example, the latest successful run on the target branch).

## Step 2. Replace Registry Host Only Under `.ko`

Use shell commands directly:

```bash
find .ko -type f -exec perl -i -pe 's|build-harbor\.alauda\.cn|registry.alauda.cn:60070|g' {} +
```

Verify the replacement scope:

```bash
grep -R -n "build-harbor\\.alauda\\.cn" .ko
```

The command output should be empty (or only expected exceptions if you intentionally kept some entries).

## Step 3. Build and Push the Operator Image (Choose One Scenario)

### Scenario A. Rebuild operator binary from current source

Use this path when Go source or patch behavior can affect the operator binary.
The same rebuild-first pattern also applies to other binary-based images (for example, webhook or controller images).

Prepare `upstream` and generate the `head` file:

```bash
make clean-patches-default apply-patches-default upgrade-go-dependencies-default
cd upstream && git rev-parse HEAD > ../head
```

`operator.Containerfile` contains `COPY head HEAD`, so the `head` file must exist before `podman build`.

Build and push:

```bash
export CUSTOM_OPERATOR_TAG="<your-custom-operator-tag>"

podman build --no-cache \
  -f .tekton/containerfiles/operator.Containerfile \
  . \
  -t build-harbor.alauda.cn/devops/tektoncd/operator/cmd/kubernetes/operator:${CUSTOM_OPERATOR_TAG}

podman push build-harbor.alauda.cn/devops/tektoncd/operator/cmd/kubernetes/operator:${CUSTOM_OPERATOR_TAG}
```

### Scenario B. Reuse base operator binary and overlay local kodata

Use this path when only `.ko/operator/kodata` changed and you do not need to rebuild the operator binary.

Build and push:

```bash
export CUSTOM_OPERATOR_TAG="<your-custom-operator-tag>"

podman build --no-cache \
  -f .tekton/containerfiles/operator-kodata-overlay.Containerfile \
  . \
  --build-arg BASE_TAG=v4.6.2-gef820f6 \
  -t build-harbor.alauda.cn/devops/tektoncd/operator/cmd/kubernetes/operator:${CUSTOM_OPERATOR_TAG}

podman push build-harbor.alauda.cn/devops/tektoncd/operator/cmd/kubernetes/operator:${CUSTOM_OPERATOR_TAG}
```

## Step 4. Trigger `to-build-bundle-image` With Explicit Tags

Set `overwrite_artifacts` with the frontend tag from `values.yaml`, and pin operator-related tags explicitly:

```bash
/test to-build-bundle-image overwrite_artifacts=".global.images.pipeline-v2-frontend_ui.tag=${UI_TAG},.global.images.operator.tag=${CUSTOM_OPERATOR_TAG},.global.images.proxy-webhook.tag=${COMMON_COMPONENT_TAG},.global.images.webhook.tag=${COMMON_COMPONENT_TAG},.global.images.tkn.tag=${COMMON_COMPONENT_TAG}" branch:${TARGET_BRANCH}
```

`to-build-bundle-image` does not build operator-related images. If tags are not pinned, the bundle may use unexpected image versions.

## Step 5. Verify Pipeline Results

In Tekton Dashboard, check:

1. `modify-values-yaml`: confirms `overwrite_artifacts` was applied.
2. `build-image`: returns the final bundle image tag.

Use that bundle image in your test environment for validation.

## Related Documentation

- [Update Frontend Images](../update-frontend/index.md)
