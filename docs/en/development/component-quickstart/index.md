---
created: '2025-01-07'
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
      # tag: a tag for the component
      tag: latest
      # digest: a digest for the component
      digest: sha256:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
      # replace_image_prefix: replace the image prefix
      # this prefix cannot contain `:@` character
      replace_image_prefix: ghcr.io/tektoncd/pipeline/controller-
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
    - `tag`: The tag for the image.
    - `digest`: The digest for the image.
    - `replace_image_prefix`: The prefix for replacing the image address.
      - Used to automatically replace some image addresses in the open-source community configuration manifest `release.yaml`.
      - This address should be as accurate as possible to avoid erroneous replacements.
      - This address cannot contain the `:@` character.
  - If there are multiple components, you can continue to add them.

#### 2.2 Initialize `Makefile` Configuration File

It is recommended to maintain a unified `Makefile` template in the `tekton-operator` code repository.

Currently, there are two files:

- `base.mk`: The base template containing all common functionalities.
  - This file should be consistent across all components.
  - If new functionalities need to be added, it is advisable to sync them back to the `tekton-operator` code repository.
- `Makefile`: The specific `Makefile` for the component, inheriting from the `base.mk` file.
  - This file primarily configures the component's unique functionalities or settings.

For example, here is the `Makefile` for `tektoncd-pipeline`:

```bash
include base.mk

# VERSION is the version of Tekton Pipeline
VERSION ?= v0.56.9

# RELEASE_YAML is the URL to get the release.yaml
RELEASE_YAML ?= https://storage.googleapis.com/tekton-releases/pipeline/previous/${VERSION}/release.yaml

# RELEASE_YAML_PATH is the path to save the release.yaml
RELEASE_YAML_PATH ?= release/release.yaml

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

#### 2.3 Initialize Open Source Configuration Manifest

Once the above `Makefile` configuration is completed, you can directly run the command `make download-release-yaml` to download the open-source community's configuration manifest.

Description:

- After the configuration manifest is downloaded, it is automatically formatted with the `yq` command.
  - This is to facilitate the subsequent automatic update of image addresses and reduce interference information in `git diff`.

#### 2.4 Initialize Component Build `Dockerfile` Configuration

The `Dockerfile` files for building each component are usually maintained in the `.tekton/dockerfiles` directory.

```dockerfile
ARG GO_BUILDER=build-harbor.alauda.cn/devops/builder-go:1.23
ARG RUNTIME=build-harbor.alauda.cn/ops/distroless-static:20220806

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
  - The base image `build-harbor.alauda.cn/ops/distroless-static:20220806` contains common users `697` and `65534`.

#### 2.5 Initialize Component Build PAC Pipeline

Currently, component builds are triggered via PAC and utilize internal templates. We only need to perform minimal configuration for rapid component builds.

As an example, here is how to configure the build pipeline for the `controller` component in `tektoncd-pipeline`:

```yaml
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: build-controller-image
  annotations:
    pipelinesascode.tekton.dev/on-comment: "^((/test-all)|(/build-controller-image)|(/test-multi.*\ build-controller-image.*))$"
    pipelinesascode.tekton.dev/on-cel-expression: |-
      # **Note** Commenting is not supported in this `on-cel-expression`. This comment is only for explanatory purposes, please remove it in the final configuration!!!
      #
      (
        # Watch for changes to relevant files and automatically trigger the pipeline.
        # Supported matching rules can be found at:
        #   - https://pipelinesascode.com/docs/guide/matchingevents/#matching-a-pipelinerun-to-specific-path-changes
        #   - https://en.wikipedia.org/wiki/Glob_%28programming%29
        #   - https://pipelinesascode.com/docs/guide/cli/#test-globbing-pattern
        # TL;DR:
        #   - `.tekton` matches all file changes in the `.tekton` directory.
        #   - `.tekton/**` matches all file changes within the `.tekton` directory.
        #   - `.tekton/.*` does not match all file changes within the `.tekton` directory.
        ".tekton/pr-build-controller-image.yaml".pathChanged() ||
        ".tekton/dockerfiles/controller.Dockerfile".pathChanged() ||
        ".tekton/patches".pathChanged() ||
        "upstream".pathChanged()
      ) && (
        # It is recommended to keep this condition to prevent unwanted triggers for changes in the `values.yaml` file.
        # Avoid automatic updates to this file which could lead to infinite triggering of the pipeline.
        # However, if the current change is on the main branch, it should still assess whether to trigger the pipeline.
        !"values.yaml".pathChanged() || source_branch.matches("^(main|master|release-.*)$")
      ) &&
      ((
        # This configuration can remain as is.
        event == "push" && (
          source_branch.matches("^(main|master|release-.*)$") ||
          target_branch.matches("^(main|master|release-.*)$") ||
          target_branch.startsWith("refs/tags/")
        )
      ) || (
        event == "pull_request" && (
          target_branch.matches("^(main|master|release-.*)$")
        )
      ))
    pipelinesascode.tekton.dev/max-keep-runs: "1"
spec:
  pipelineRef:
    # Using the pipeline template. For specific definitions and explanations, refer to:
    #   https://tekton-hub.alauda.cn/alauda/pipeline/clone-image-build-test-scan
    resolver: hub
    params:
    - name: catalog
      value: alauda
    - name: type
      value: tekton
    - name: kind
      value: pipeline
    - name: name
      value: clone-image-build-test-scan
    - name: version
      value: "0.2"

  params:
    # These are general configurations and do not need modification.
    - name: git-url
      value: "{{ repo_url }}"
    - name: git-revision
      value: "{{ source_branch }}"
    - name: git-commit
      value: "{{ revision }}"

    # **Must adjust** to the actual image repository being built
    - name: image-repository
      value: build-harbor.alauda.cn/test/devops/tektoncd/pipeline/controller

    # **Must adjust** to the actual Dockerfile being built
    - name: dockerfile-path
      value: .tekton/dockerfiles/controller.Dockerfile

    # **Must adjust** to the actual build context for the image
    - name: context
      value: "."

    # **Must adjust** to the actual file change list to monitor
    # **Note** The pipeline will calculate the last modified commit sha based on changes to these files.
    #          This sha will be used in the image label for commit information and will also affect the final artifact's tag.
    - name: file-list-for-commit-sha
      value:
        - upstream
        - .tekton/patches
        - .tekton/dockerfiles/controller.Dockerfile
        - .tekton/pr-build-controller-image.yaml

    # **Must adjust** to the actual operations needed
    - name: update-files-based-on-image
      value: |
        # The script can use this environment variable:
        #    - IMAGE: the image URL with tag and digest, such as `registry.alauda.cn:60080/devops/nonroot/alauda-docker-buildx:latest@sha256:1234567890`
        #    - IMAGE_URL: the image URL without tag and digest, such as `registry.alauda.cn:60080/devops/nonroot/alauda-docker-buildx`
        #    - IMAGE_TAG: the image tag, such as `latest`
        #    - IMAGE_DIGEST: the image digest, such as `sha256:1234567890`
        #    - LAST_CHANGED_COMMIT: the last changed commit sha

        # Use yq from the base image to avoid automatic installation in Makefile.
        export YQ=$(which yq)

        # Update the `values.yaml` file with the complete image information obtained from the build.
        # The scripts used here are present in the base image. For logic details, refer to:
        #   - https://gitlab-ce.alauda.cn/ops/edge-devops-task/-/blob/master/images/yq/script/update_image_version.sh
        #   - https://gitlab-ce.alauda.cn/ops/edge-devops-task/blob/master/images/yq/script/replace_images_by_values.sh

        echo "update_image_version.sh values.yaml ${IMAGE}"
        update_image_version.sh values.yaml ${IMAGE}

        # **Important** Update the component's version number
        # It will be based on the calculated last changed commit sha, used as the version suffix.

        # Get the current version and remove the -.* suffix
        OLD_VERSION=$(yq eval '.global.version' values.yaml)
        # Use the short commit sha as the version suffix
        export SUFFIX=${LAST_CHANGED_COMMIT:0:7}
        echo "update component version ${OLD_VERSION} suffix to ${SUFFIX}"
        make update-component-version

        # **Important** Update the `release.yaml` file based on the latest `values.yaml` file.

        echo "replace images in release/release.yaml"
        replace_images_by_values.sh release/release.yaml controller

    # **Must adjust** If the image can be initially verified through execution commands, it can be added here.
    - name: test-script
      value: ""

    # **Must adjust** Add as needed. The `prepare-tools-image` and `prepare-command` are for pre-build tasks.
    # For instance, a few tasks performed here are:
    #   - Generate the `head` file containing the commit sha of the `upstream` directory. This is generally used in the `Dockerfile`.
    #   - Set Golang environment variables
    #   - Update go mod dependencies to fix security issues (optional)

    - name: prepare-tools-image
      value: "build-harbor.alauda.cn/devops/builder-go:1.23"

    - name: prepare-command
      value: |
        #!/bin/bash
        set -ex

        # Generate head file containing the commit sha of the upstream directory
        cd upstream

        git rev-parse HEAD > ../head && cat ../head

        export GOPROXY=https://build-nexus.alauda.cn/repository/golang/,https://goproxy.cn,direct
        export CGO_ENABLED=0
        export GONOSUMDB=*
        export GOMAXPROCS=4

        export GOCACHE=/tmp/.cache/go-build
        mkdir -p $GOCACHE

        # Upgrade go mod dependencies
        go get github.com/docker/docker@v25.0.7
        go get github.com/cloudevents/sdk-go/v2@v2.15.2
        go get github.com/Azure/azure-sdk-for-go/sdk/azidentity@v1.6.0
        go get github.com/hashicorp/go-retryablehttp@v0.7.7
        go get golang.org/x/crypto@v0.31.0
        go get google.golang.org/protobuf@v1.33.0
        go get gopkg.in/go-jose/go-jose.v2@v2.6.3

        go mod tidy
        go mod vendor
        git diff go.mod

    # **Must adjust** Add as needed. The `pre-commit-script` is for operations before committing.
    - name: pre-commit-script
      value: |
        # remove `head` file
        rm -f head
        #
        # revert upstream directory to avoid unnecessary changes
        cd upstream
        git checkout .
        cd .. # go back to the root directory

    # **Must adjust** Add as needed. If image scanning is not required, this configuration can be enabled.
    # - name: ignore-trivy-scan
    #   value: "true"

  # The configurations below generally do not need modification.
  workspaces:
    - name: source
      volumeClaimTemplate:
        spec:
          accessModes:
            - ReadWriteMany
          resources:
            requests:
              storage: 1Gi
    - name: dockerconfig
      secret:
        secretName: build-harbor.kauto.docfj
    # This secret will be replaced by the pac controller
    - name: basic-auth
      secret:
        secretName: "{{ git_auth_secret }}"
    - name: gitversion-config
      configMap:
        name: gitversion-config

  taskRunTemplate:
    # Ensure that all tasks run as a non-root user.
    podTemplate:
      securityContext:
        runAsUser: 65532
        runAsGroup: 65532
        fsGroup: 65532
        fsGroupChangePolicy: "OnRootMismatch"

  taskRunSpecs:
    - pipelineTaskName: prepare-build
      computeResources:
        limits:
          cpu: '4'
          memory: 4Gi
        requests:
          cpu: '2'
          memory: 2Gi
```

The functionalities achieved by this pipeline are:

- `git-clone` Pulls the code
- `calculate-commit-sha` `git-version` `generate-tags` Calculates the image tag
- `prepare-build` Prepares for the image build
  - E.g., updating certain files
- `build-image` Constructs the image
- `test-image` Tests the image (optional)
- `image-scan` Scans the image (optional)
- `update-files-based-on-image` Based on the built image, updates files
  - E.g., updates the constructed image in `values.yaml` and other files
- `commit` Commits local changes (optional)
- `trigger-pipeline` Triggers downstream pipelines (optional)

### 3. Trigger the Pipeline

After completing the preparation work, the pipeline can be triggered via PAC.

This can be done by creating a PR or by commenting on the PR or commit.

### 4. Register with Tekton Operator

The expectation is that the `Tektoncd-Operator` pipeline automatically fetches the configuration manifests of various components (usually the YAML configurations in the `release` directory) and updates them in the `Tektoncd-Operator` code repository. This ensures that the next build of `Tektoncd-Operator` can include the corresponding versions of the associated components.

To facilitate this retrieval, add the corresponding component information in the `components.yaml` file under the `Tektoncd-Operator` code repository.

```yaml
pipeline:
  # The repository and branch to use for the pipeline component
  github: AlaudaDevops/tektoncd-pipeline
  # The revision to use to fetch for the component
  revision: main
  # This version will be automatically fetched from the corresponding branch of the code repository
  # It reads the `.global.version` field in values.yaml
  version: v0.66.0
```

Description:

- github: The repository address for the component's code, formatted as `org/repo`.
- revision: The branch of the component's code repository.
  - Can be a branch, tag, or commit id.
- version: The version number of the component.
  - Typically read from the corresponding `values.yaml` file in the code repository and corresponding `revision`.
  - This field will be automatically updated with each configuration fetch, so it generally doesn't require manual maintenance.

### 5. Trigger the Fetching Pipeline to Get the Latest Subcomponent Versions and Configurations

Currently, there is no mechanism to automatically update the latest versions of subcomponents into the `Tektoncd-Operator` code repository.
If there is interest, there are ways to achieve this.

The current manual method is to comment on the latest commit of the corresponding branch in the `Tetoncd-Operator` code repository to trigger the fetching pipeline.

    /test to-fetch-component-releases

Once the pipeline executes successfully, it will automatically update the version information in the `components.yaml` file, update the dependent images in `values.yaml`, and update the subcomponent configuration manifests in the `.ko/operator/kodata/` directory, then commit the changes back to the code repository.

This commit will automatically trigger the `Tektoncd-Operator` pipeline, synchronizing the newly built `bundle` image to the [`devops-artifact`](https://github.com/AlaudaDevops/devops-artifact/blob/main/values.yaml) repository.

## To Be Improved

### 1. Branch Management Strategy

### 2. How to Manage the Patches Package
