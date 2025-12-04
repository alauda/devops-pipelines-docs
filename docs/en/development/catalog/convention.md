---
weight: 10
status: proposed
title: Catalog Conventions
creation-date: "2025-02-20"
category: docs
authors:
  - "@qingliu"
---

# Catalog Conventions

## Task Conventions

### 1. Follow Community [Catalog](https://github.com/tektoncd/catalog) Conventions

Catalog Structure

1. Each resource follows the following structure

    ```
    ./task/                     👈 the kind of the resource

        /argocd                 👈 definition file must have same name
           /0.1
             /OWNERS            👈 owners of this resource
             /README.md
             /DEVELOPMENT.md    👈 development guide
             /argocd.yaml       👈 the file name should match the resource name
             /samples/deploy-to-k8s.yaml
           /0.2/...

        /golang-build
           /OWNERS
           /README.md
           /0.1
             /README.md
             /golang-build.yaml
             /samples/golang-build.yaml
    ```

2. Resource YAML file includes following changes
  *  Labels include the version of the resource.
  *  Annotations include `minimum pipeline version` supported by the resource,
     `tags` associated with the resource and `displayName` of the resource

     ```yaml
   
      labels:
         app.kubernetes.io/version: "0.1"                 👈 Version of the resource, has to equal to the version in the file path, e.g. version == "0.1" in "example-task/0.1/example-task.yaml"
   
       annotations:
         tekton.dev/pipelines.minVersion: "0.12.1"        👈 Min Version of pipeline resource is compatible
         tekton.dev/categories: CLI                       👈 Comma separated list of categories
         tekton.dev/tags: "ansible, cli"                  👈 Comma separated list of tags
         tekton.dev/displayName: "Ansible Tower Cli"      👈 displayName can be optional
         tekton.dev/platforms: "linux/amd64,linux/s390x"  👈 Comma separated list of platforms, can be optional
         tekton.dev/icon: data:image/svg+xml;base64,{{ base64 icon data }} 👈 The base64 encoded svg icon, can be optional
   
     spec:
       description: |-
         ansible-tower-cli task simplifies
         workflow, jobs, manage users...                  👈 Summary
   
         Ansible Tower (formerly 'AWX') is a ...
   
     ```

**Note** : Categories are a generalized list and are maintained by Hub. To add new categories, please follow the procedure mentioned [here](https://github.com/tektoncd/hub/blob/main/docs/ADD_NEW_CATEGORY.md).

### 2. Use v1 Version of Task

Currently `tekton.dev/v1` is the default version, and this version does not have the `ClusterTask` resource type, therefore we recommend using the `v1` version of Task.

### 3. Specify Default Resources `computeResources` for Task

It is recommended that `Task` has a default `computeResources`, and users can override it through `TaskRun` if they need to adjust.

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: foo
spec:
  steps:
    - name: sonar-properties-create
      computeResources:
        requests:
          cpu: "1"
          memory: "1Gi"
        limits:
          cpu: "2"
          memory: "2Gi"
```

```yaml
apiVersion: tekton.dev/v1
kind: TaskRun
metadata:
  name: foo-run
spec:
  computeResources:
    requests:
      cpu: "2"
      memory: "2Gi"
    limits:
      cpu: "4"
      memory: "4Gi"
```

### 4. Image Management for Catalog Tasks

Catalog Tasks that expose configurable runtime images must publish metadata and defaults consistently so the UI and controllers can discover them.

#### Configurable Image Metadata

Represent each image option with a single `ConfigMap` scoped to one Task and one Task version. Include the human-readable name and full image reference, and add labels so the UI/controller can filter by Task/version.

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

Key fields and labels:
- `data.name`: dropdown label.
- `data.image`: full image reference.
- `catalog.tekton.dev/source`: identifies the source.
- `catalog.tekton.dev/tool-image-<tool>`: identifies the tool image for the Task.
- `catalog.tekton.dev/tool-image-run-script`: identifies the tool image for `run-script` Task.

#### Catalog Defaults and Tagging

- Keep existing `image` parameter defaults in Tasks; do not clear them.
- Use minor-only tags for catalog images (for example, `v7.0`) and publish a `latest` alias for the newest minor release.
- Publish one `ConfigMap` per runtime version with `name` and `image` data plus Task/version labels; keep defaults on the current minor until a new Task minor is added.
- When introducing a new runtime minor (for example, Python 3.14), keep the older Task minor default on the previous image (3.13), add a new Task minor with no default image to force explicit selection, and add the corresponding per-version `ConfigMap` entries.

  ```yaml
  global:
    images:
      python-3_13:
        repository: devops/tektoncd/hub/python
        tag: v3.13
      python-latest:
        repository: devops/tektoncd/hub/python
        tag: latest
  ```

#### Custom Image Builds

If Tasks in the catalog depend on custom images, provide the `Dockerfile` and build pipelines in the catalog so they can be reproduced.

- Build environments are stored in the `images/{image-name}` directory.
- Image build pipeline orchestration files are stored in `.tekton/images/build-{image-name}.yaml`.

#### Image Security

- For security considerations, it is recommended to create a `nonroot` user with ID `65532` as the default user when the image is finally executed.
- It is also recommended to add `USER 65532` instead of `USER nonroot` in the `Dockerfile` to specify this user.
  - This is because when a Pod specifies `runAsNonRoot`, it cannot confirm that the user is non-root when using `USER nonroot`, which will result in a `CreateContainerConfigError`.

    ```dockerfile
    # Add a non-root user
    
    # For Alpine images
    RUN adduser -u 65532 -h /home/nonroot -D nonroot -s /sbin/nologin
    
    # For Debian, Ubuntu images
    RUN adduser --home /home/nonroot --uid 65532 nonroot --shell /usr/sbin/nologin --disabled-password --gecos ""
    
    # Set the default user
    USER 65532
    ```

#### Image Tags

Follow the catalog tagging strategy above for custom builds (minor-only tags plus a `latest` alias). If the image is derived from a specific community version, include that upstream version in the tag prefix when needed for traceability (for example, `v0.56.0-v7.0`).

#### Image Path

It is recommended to uniformly use `/devops/tektoncd/hub/` as the image path prefix for convenient image management in the future.

### 5. Not Recommended to Specify `runAsUser` in Task Definitions that Support User Custom Images

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: foo
spec:
  steps:
    - name: bar
      securityContext:
        runAsNonRoot: true
        # runAsUser: 65532  # Not recommended to specify in Task
```

This is because after specifying the `runAsUser` configuration in the `step` of a `Task`, it is equivalent to configuring this property for a specific `Container` of the Pod.
However, the `podTemplate` of `TaskRun` can currently only override this configuration at the `Pod` level and cannot override this configuration for a specific `Container`.

If the user's base image must require a specific user (non-65532) to work properly, then this configuration may prevent users from using this `Task`.

#### Exceptions

For general script execution Tasks like `run-script`, **it is recommended to specify `runAsUser` in the Task** for the following reasons:

1. The main purpose of such Tasks is to execute general scripts, and users usually don't need to customize base images for them
2. Specifying `runAsUser` allows users to:
    - Directly use various standard images
    - Avoid additional configuration in `TaskRun` or `PipelineRun`
    - Improve ease of use

> **Note**: This recommendation only applies to general script execution Tasks, other types of Tasks should still follow the above conventions.

### 6. Tasks Need Integration Test Coverage

Integration test pipelines can be placed in the `.tekton/integrations/{task-name}.yaml` directory.

### 7. Unified Use of `registry.alauda.cn:60070` for Image Registry Addresses Referenced in Tasks

Although the currently built images are usually `build-harbor.alauda.cn`, considering that this image address is inconvenient for integration testing.
Therefore, it is temporarily recommended to uniformly use `registry.alauda.cn:60070` as the image registry address in Tasks.

### 8. Task Display Names

Task display names follow PascalCase convention, meaning the first letter is capitalized.

| Description                             | Bad Case          | Good Case         |
| --------------------------------------- | ----------------- | ----------------- |
| First letter capitalized                | buildah           | Buildah           |
| First letter of each word capitalized   | Sonarqube scanner | Sonarqube Scanner |
| Multiple words separated by spaces, not `-`, `_` | RunScript         | Run Script        |

### 9. Task HTTPS Certificates Handling

When adding a new Task, cover the following cases:

- Allow skipping certificate verification for HTTPS: expose a toggle parameter and clearly document the risks and when to use it.
- Trust HTTPS via user-provided certificates: expose a workspace for mounting custom CAs/truststores.
- If the tool uses a “full replacement” trust-store strategy: implement append/merge logic in the Task so user certificates are added to the default trust chain rather than overwriting it, preventing breaks to other HTTPS endpoints and improving UX.

### 10. Task Overview Templates (ConfigMap + Template)

We support two overview rendering paths as described in [TEP-0003: PipelineRun Support Markdown Output](../../teps/0003_pipelinerun_markdown_output.md) and [TEP-0004: Task Overview Template Rendering](../../teps/catalog/0004-task-result-template.md) :

1. A `overview-markdown` Task result containing fully-rendered markdown.
2. A ConfigMap-backed template (for example, using the EJS engine) that consumes structured Task results.

For catalog contributors, we adopt the following conventions:

- **Platform-provided / curated overview templates MUST use the ConfigMap + template path.**
  - Do **not** let catalog Tasks we own write to a `overview-markdown` result by default.
  - Tasks that support user-defined scripts should, where possible, provide an empty `overview-markdown` result for users to use.
  - Treat `overview-markdown` as a user extension point: if a Pipeline or Task wants to override the UI, it can emit this result and the UI will prefer it over any ConfigMap template.

- **ConfigMap location and labels**

  - ConfigMaps that contain EJS overview templates MUST be stored under the [catalog](https://github.com/AlaudaDevops/catalog) repository's `config/catalog/` directory, and be shipped together with other catalog manifests.
  - Templates are deployed into the `kube-public` namespace so any dashboard instance can read them.
  - Each ConfigMap corresponds to one Task (and version) that owns the overview template and MUST carry the following labels so the UI can discover it:

    ```yaml
    # config/catalog/sonarqube-scanner-0.5-overview-template.yaml
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: sonarqube-scanner-0.5-overview-template
      namespace: kube-public
      annotations:
        # keep namespace hardcoded to kube-public even when InstallerSets perform ReplaceNamespace
        operator.tekton.dev/preserve-namespace: "true"
      labels:
        # task name
        style.tekton.dev/overview-template-task: sonarqube-scanner
        # task version
        style.tekton.dev/overview-template-task-version: "0.5"
        # template engine
        style.tekton.dev/overview-template-engine: ejs
    data:
      # main EJS template entry
      template.ejs: |
        <!-- EJS template content -->
    ```

- **Task annotations for template binding**

  - Tasks that use a ConfigMap-based overview MUST declare which template to use and which result(s) provide the data.
  - Use annotations on the Task to tell the UI how to find the template and which results to merge:

    ```yaml
    apiVersion: tekton.dev/v1
    kind: Task
    metadata:
      name: sonarqube-scanner
      annotations:
        # label selector to find the ConfigMap under kube-public
        style.tekton.dev/overview-template-selector: "style.tekton.dev/overview-template-task=sonarqube-scanner,style.tekton.dev/overview-template-task-version=0.5"
  
        # one or more result names that provide structured metrics
        # single result:
        style.tekton.dev/overview-template-result-key: CODE_SCAN_METRICS
  
        # optional: multiple results and aliasing (advanced)
        # style.tekton.dev/overview-template-result-key: CODE_SCAN_METRICS:metrics,SCAN_RESULT_URL,SCAN_PROJECT
    ```

  - `overview-template-selector` tells the UI which ConfigMap to fetch (via label selector).
  - `overview-template-result-key` identifies the Task result (or comma-separated list of results) that carries the structured metrics.

- **Result contract and `overview-markdown` usage**

  - The result should be:
    - Compact enough to stay within the effective per-container termination-message budget.
    - Stable and documented in the Task's `README.md` so template authors and other consumers know which keys are available.
  - Do **not** store rendered HTML in results or annotations; only store structured data (metrics, URLs, labels).
  - `overview-markdown` is reserved for user-authored or downstream custom views. The UI always prefers `overview-markdown` over ConfigMap templates so that:
    - Catalog contributors use ConfigMap templates for pre-baked views.
    - Users can still override the overview by emitting their own `overview-markdown` result from Pipelines or Tasks that they control.
