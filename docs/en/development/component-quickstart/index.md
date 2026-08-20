---
created: '2025-01-07'
updated: '2025-07-13'
weight: 10
---

# Component Quick Start

## Background

The Tekton Operator carries multiple components, each with its own code repository and version plan.

The development process for each plugin is similar. This document describes how to quickly initialize a plugin and register it with the Tekton Operator.

## Principles

- Strive to unify processes and reduce repetitive work.

## Quick Start

### 1. Prerequisites

#### 1.1 Initialize the Code Repository

Create a new repository under <https://github.com/AlaudaDevops> starting with `tektoncd-`, followed by the name of the corresponding open-source component, such as `tektoncd-pipeline`.

#### 1.2 Initialize Submodule

Add the open-source component's code repository as a submodule in the new repository, currently agreed to be placed under the `upstream` directory.

It is recommended to choose a stable release branch, such as `release-v0.56.x`.

```yaml
$ git submodule add -b release-v0.56.x https://github.com/tektoncd/pipeline upstream
```

#### 1.3 Initialize Documentation

Refer to the platform's unified [documentation development](https://product-doc-guide.alauda.cn/02_quick_start/01_doc_dev.html) specifications to initialize the documentation directory.

Typically, the steps are:

1. Install dependencies: `npm install -g @alauda/doom`

2. Initialize the documentation directory: `doom new product-doc:site`

3. Preview locally: `npm run dev`

#### 1.4 Prepare PAC Configuration - Create `Repository` Configuration

Currently, pipelines are managed and triggered through PAC, so related configurations need to be set up briefly.

Refer to this file: <https://gitlab-ce.alauda.cn/devops/edge/-/blob/master/cluster/devops/templates/devops/pac-tektoncd-pipeline.yaml>

The expectation is that this configuration will be uniformly managed through the above `gitops` code repository.

1.5 Required Configuration File List

| File                        | Source                | Purpose                                                    |
|-----------------------------|-----------------------|------------------------------------------------------------|
| **base.mk**                 | Copy from other project | Common make targets (check/test/manifests/deploy, etc.)     |
| **Makefile**                | Create new            | Override project-specific settings such as manifests/dist/deploy |
| **renovate.json**           | Copy from template    | Dependency auto-update                                      |
| **sonar-project.properties**| Copy from template    | Code quality checks                                         |
| **.golangci.yml**           | Copy from template    | Static code analysis                                        |
| **go.mod & go.sum**         | `go mod init`         | Dependency management                                       |
| **hack/boilerplate.go.txt** | Copy from template    | License header template                                     |
| **cmd/controller/rbac.go**  | Create new            | RBAC kubebuilder annotations                                |

### 2. Scaffolding Configuration

#### 2.1 Initialize Configuration File `values.yaml`

```yaml
# global: root location for common arguments
global:
  registry:
    # address: registry address
    address: build-harbor.alauda.cn
  # version is the component version
  #   1. used by tekton-operator, records the version of this component
  #   2. sync to the configmap `pipelines-info`
  version: "v0.56.9"
  # images records related images and components
  # used to store the last changed commit for each component
  images:
    controller:
      # repository: image repository for the image
      repository: devops/tektoncd/pipeline/controller
      # tag: image tag
      tag: latest
```

Description:

- `global.registry.address`: The address for the image repository.
  - Typically `build-harbor.alauda.cn`.
- `global.version`: The component's version number.
  - Initially, this is the version number of the open-source component, and this configuration will be automatically updated in subsequent pipelines.
    - The tekton-operator determines whether to update this component based on its version number. Thus, as long as the configuration manifest changes, the component's **version** must also change to trigger the component's automatic update.
- `global.images`: The image information for dependent components.
  - `controller`: The name of the component.
    - `repository`: The address of the image repository.
    - `tag`: The image tag.
  - If there are multiple components, you can continue to add them.

:::note
Currently, `values.yaml` is only used to record the dependent images, which is convenient for summarizing and packaging in `tektoncd-operator`.

**The image tag should be automatically updated by the pipeline, not manually.**
:::

#### 2.2 Initialize Configuration Directory Structure

Create the configuration directory structure under the `config` directory. This is where the final `release.yaml` files are generated through kustomize.

```bash
config/
├── pipeline/
│   ├── kustomization.yaml
│   ├── release.yaml          # Community release.yaml
│   └── fsgroup-config-patch.yaml     # Custom patches
└── ...
```

**Important**: The image replacement configuration is now managed in the `config` directory through kustomize, not in `values.yaml`. This provides better separation of concerns and more flexible configuration management.

Example `kustomization.yaml` for image replacement:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- release.yaml
images:
- name: ghcr.io/tektoncd/pipeline/controller
  newName: build-harbor.alauda.cn/devops/tektoncd/pipeline/controller
  newTag: latest
```

#### 2.3 Initialize `Makefile` Configuration File

It is recommended to maintain a unified `Makefile` template in the `tekton-operator` code repository.

Currently, there are two files:

- `base.mk`: The base template containing all common functionalities.
  - This file should be consistent across all components.
  - If new functionalities need to be added, it is advisable to sync them back to the `tekton-operator` code repository.
- `Makefile`: The specific `Makefile` for the component, inheriting from the `base.mk` file.
  - This file primarily configures the component's unique functionalities or settings.

For example, here is the `Makefile` for `tektoncd-pipeline`:

> Ref : <https://github.com/AlaudaDevops/tektoncd-pipeline/blob/main/Makefile>

```bash
include base.mk

# VERSION is the version of Tekton Pipeline
VERSION ?= v0.56.9

# RELEASE_YAML is the URL to get the release.yaml
RELEASE_YAML ?= https://storage.googleapis.com/tekton-releases/pipeline/previous/${VERSION}/release.yaml

# RELEASE_YAML_PATH is the path to save the release.yaml
RELEASE_YAML_PATH ?= config/pipeline/release.yaml

# VERSION_CONFIGMAP_NAME is the name of the configmap that contains the component version
VERSION_CONFIGMAP_NAME ?= pipelines-info
```

Description:

- `VERSION`: The current version number of the component. **Important**
  - This version number will be used to fetch the open-source community's configuration manifest `release.yaml`.
  - It will update the `global.version` field in `values.yaml` and the component version information in the open-source configuration manifest `release.yaml`.
- `RELEASE_YAML`: The address of the open-source community's configuration manifest.
- `RELEASE_YAML_PATH`: The local saved configuration manifest address.
  - It **must** be placed under the `release` directory, and the filename can be customized.
- `VERSION_CONFIGMAP_NAME`: The name of the `configmap` that records the component version number in the configuration manifest.
  - For instance, the configuration file name for the `tektoncd-pipeline` component is `pipelines-info`.

    ```yaml
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: pipelines-info
      namespace: tekton-pipelines
      labels:
        app.kubernetes.io/instance: default
        app.kubernetes.io/part-of: tekton-pipelines
    data:
      # Contains pipelines version which can be queried by external
      # tools such as CLI. Elevated permissions are already given to
      # this ConfigMap such that even if we don't have access to
      # other resources in the namespace we still can have access to
      # this ConfigMap.
      version: v0.56.9
    ```

#### 2.4 Initialize Open Source Configuration Manifest

Once the above `Makefile` configuration is completed, you can directly run the command `make download-release-yaml` to download the open-source community's configuration manifest.

Description:

- After the configuration manifest is downloaded, it is automatically formatted with the `yq` command.
  - This is to facilitate the subsequent automatic update of image addresses and reduce interference information in `git diff`.

#### 2.5 Initialize Component Build `Containerfile` Configuration

The `Containerfile` files for building each component are usually maintained in the `.tekton/containerfiles` directory.

```text
ARG GO_BUILDER=build-harbor.alauda.cn/devops/nonroot/builder-go:latest
ARG RUNTIME=build-harbor.alauda.cn/ops/distroless-static:12-alauda-202502271510

FROM $GO_BUILDER AS builder

WORKDIR /go/src/github.com/tektoncd/pipeline
COPY upstream .
COPY .tekton/patches patches/
RUN set -e; for f in patches/*.patch; do echo ${f}; [[ -f ${f} ]] || continue; git apply ${f}; done
COPY head HEAD
ENV GODEBUG="http2server=0" \
    GOMAXPROCS=4 \
	GOFLAGS=-buildvcs=false \
	CGO_ENABLED=0
RUN go build -trimpath -ldflags="-w -s -X 'knative.dev/pkg/changeset.rev=$(cat HEAD)'" -mod=vendor -tags disable_gcp -v -o /tmp/controller \
    ./cmd/controller

FROM $RUNTIME
ARG VERSION=pipeline-main

ENV CONTROLLER=/usr/local/bin/controller \
    KO_APP=/ko-app \
    KO_DATA_PATH=/kodata

COPY --from=builder /tmp/controller /ko-app/controller
COPY head ${KO_DATA_PATH}/HEAD

USER 65534

ENTRYPOINT ["/ko-app/controller"]
```

Description:

- Strive for the image to be reproducibly built.
  - For example, specifying the Go build parameters.
- Run as a non-root user.
  - Tekton components have security restrictions; running as a root user may lead to startup failures.
- User 65534 is an internal convention.
  - The base image `build-harbor.alauda.cn/ops/distroless-static:12-alauda-202502271510` contains common users `697` and `65534`.

#### 2.6 Initialize All-in-One Build PAC Pipeline

Configure the all-in-one build pipeline that builds all components together:

:::note
The current build strategy has changed to an all-in-one approach, which is more efficient and recommended. Individual component builds are no longer recommended.
:::

Ref : <https://github.com/AlaudaDevops/tektoncd-pipeline/blob/main/.tekton/tp-all-in-one.yaml>

**Pipeline Main Workflow:**

1. **Git Clone Phase**
   - Clone the code repository to the workspace

2. **Golang Check Phase**
   - Apply patches and upgrade Go dependencies
   - **Code Testing**: Run `go test` for unit tests and integration tests
   - **Code Quality Check**: Use `golangci-lint` for static code analysis
   - **Security Vulnerability Check**: Use `govulncheck` to check dependency security vulnerabilities
   - **Code Coverage**: Generate test coverage reports
   - **SonarQube Analysis**: Upload code quality reports to SonarQube

3. **Image Build Phase**
   - Build multiple component images in parallel (e.g., tkn, proxy, webhook, operator)
   - Each image build includes:
     - Build OCI images
     - Update image tag in `values.yaml` and `config` directory

4. **Artifact Upload Phase**
   - Generate `values.yaml` and `release.yaml` files
   - Upload artifacts to Nexus repository

### 3. Register with Tekton Operator

The component registration is now managed through the `components.yaml` file in the TektonCD Operator repository. This file defines the strategy for fetching component release files.

More information can be found in [Operator Integration Guide](../component-upgrade-guide/operator-integration.md)

### 4. Branch Management {#4-branch-management}

#### 4.1 Branch Strategy

:::note
Once a release branch is created, new features are not allowed to be added. Only bug fixes and security issues are allowed.
:::

All components follow a unified branch management strategy:

**Branch Types:**

- `main`: Development branch for code adaptation and testing
- `release-*`: Release branches created after passing the `tektoncd-operator` release process

**Branch Creation Process:**

1. **Development Phase**: Complete code adaptation and testing on `main` branch
2. **Release Creation**: After daily release validation is completed and before `tektoncd-operator` code freeze, create `release-*` branch from `main`

**Branch Naming Convention:**

**Community Components** (e.g., `tektoncd-pipeline`, `tektoncd-trigger`, `tektoncd-chains`):

- Use `release-{major}.{minor}` format to align with upstream community versions
- Example: `release-0.65` branch corresponds to upstream `release-v0.65.x` version

**Self-Developed Components**:

- Use `release-{feature-milestone}` format based on functional milestones.
- `tektoncd-operator` follows this strategy because it is the orchestration component for the ACP DevOps Tekton stack.
- The catalog is now maintained as part of the `artifacthub-shim` delivery path instead of being treated as a Tekton Operator built-in runtime component.
- `hubs-wrapper` and Tekton Hub runtime are no longer new component templates for ACP DevOps 4.14 and later.

**Exception Cases:**

**tektoncd-operator**: Although it is a community component, as a core component of `Alauda DevOps Pipelines`, it follows the self-developed component branch management strategy:

- Use `release-{feature-milestone}` format based on functional milestones
- Examples: `release-4.0`, `release-4.1` for new features
- This exception is made because `tektoncd-operator` serves as the central orchestration component for the entire Tekton ecosystem and requires more flexible release management to align with Alauda DevOps Pipelines' development cycle

#### 4.2 Benefits

This dual branch management strategy provides several key benefits:

##### For Community Components

- **Clear Component Version Dependencies**: Each `release-*` branch clearly indicates which upstream component version it depends on
- **Shared Artifact Reuse**: Multiple Tekton Operator versions using the same upstream component version can share artifacts
- **Simplified Maintenance**: Security patches and bug fixes can be applied once and shared across compatible versions

##### For Self-Developed Components

- **Flexible Release Schedule**: Release frequency can be based on functional needs rather than `tektoncd-operator` version alignment
- **Reduced Maintenance Overhead**: Stable components can maintain a single release branch for extended periods if no new features are needed
- **Feature-Driven Development**: Branch creation is driven by actual functional requirements rather than arbitrary version numbers

#### 4.3 Limitations

This branch management strategy also has some limitations:

##### Increased Documentation Synchronization Complexity

- Previously, documentation could be synchronized directly using the same branch name as `tektoncd-operator`
- Now, documentation synchronization needs to be based on the actual versions specified in `components.yaml`
- This requires additional coordination and verification to ensure documentation matches the correct component versions

### 5. Tag Management

Tag management is designed to better manage component versions and ensure that artifacts with the same commit maintain consistent tags and digests after creating new release branches.

#### 5.1 Tag Strategy Overview

The tag strategy varies between community components and self-developed components:

**Community Components** (e.g., `tektoncd-pipeline`, `tektoncd-trigger`, `tektoncd-chains`):

- **No tags needed** in the code repository
- Version prefixes use community versions defined in the `Makefile`
- Artifact versioning is managed through the community version numbers

**Self-Developed Components** (e.g., `tektoncd-operator`):

- **Strict tag management** is required
- Tags are created on the next commit in `main` branch after creating a release branch
- Follows semantic versioning with alpha pre-releases for development

#### 5.2 Tag Management for Self-Developed Components

##### 5.2.1 Tag Creation Timing

Tags should be created at the **first commit that differs from the release branch**, not on the common commit.

**Example Workflow:**

1. **After creating `release-4.1` branch** from `main`
2. **On the next new commit** in `main` branch (not the common commit)
3. **Create alpha tag**: `v4.2.0-alpha.0`

This ensures that the `main` branch generates version numbers like `v4.2.0-g{commit-hash}`, which will have the same prefix as future `release-4.2` branch artifacts.

##### 5.2.1 Tag Naming Convention

**Release Tags (on `release-*` branch):**

- Format: `v{major}.{minor}.{patch}`
- Examples: `v4.1.0`, `v4.1.1`
- Created only after release validation is completed
- Purpose: Marks stable releases

##### 5.2.2 Tag Management Process

**Step 1: Create Release Branch**

```bash
# Create release branch from main
git checkout -b release-4.1 main
git push origin release-4.1
```

**Step 2: Create Alpha Tag on Main**

```bash
# Switch back to main and make a new commit
git checkout main
# ... make changes ...
git commit -m "feat: prepare for v4.2.0 development"
git push origin main

# Create alpha tag on the new commit
git tag v4.2.0-alpha.0
git push origin v4.2.0-alpha.0
```

**Step 3: Create Release Tag After Validation**

```bash
# After release validation on release-4.1 branch
git checkout release-4.1
git tag v4.1.0
git push origin v4.1.0
```

#### 5.3 Benefits of This Tag Strategy

1. **Version Consistency**: Ensures that the same commit produces consistent artifact versions across branches
2. **Clear Development Progress**: Alpha tags clearly indicate development milestones
3. **Stable Release Marking**: Release tags only appear after thorough validation
4. **Artifact Reusability**: Prevents unnecessary rebuilds of identical commits
