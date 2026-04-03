# Buildah Task

- [Summary](#summary)
- [Motivation](#motivation)
  - [Goals](#goals)
  - [Non-Goals](#non-goals)
  - [Use Cases](#use-cases)
  - [Requirements](#requirements)
- [Design Details](#design-details)
  - [Performance](#performance)
  - [Test Plan](#test-plan)
  - [Infrastructure Needed](#infrastructure-needed)
- [References](#references)

## Summary

This proposal aims to create an Image Task for executing container image build operations in Tekton Pipeline.

## Motivation

Currently, there are multiple image building tools in the community, such as Docker, Buildah, BuildKit, etc., each with different advantages and disadvantages.

| Tool | Caching Mechanism | Configuration Complexity | Build Speed | Community | Flexibility | Daemon Compatibility | Multi-Architecture Build |
|------|------------------|-------------------------|-------------|-----------|-------------|---------------------|-------------------------|
| Docker | Layer caching, medium efficiency | Simple (Containerfile) | Fast | Very large (mainstream) | Medium (depends on Containerfile) | Requires Docker Daemon | Supported (requires BuildKit or docker buildx) |
| Buildah | Manual cache management, high flexibility | Medium (CLI commands) | Medium | Medium (Red Hat) | Very high (layer-by-layer control) | No Daemon required | Supported (using QEMU) |
| BuildKit | Advanced caching (remote/parallel/incremental) | High (requires separate config files) | Very fast | Large (cloud-native) | Very high (multi-platform support) | Optional mode (Daemonless) | Supported (supports cross-compilation and QEMU) |
| S2I | Depends on builder cache, limited optimization | Low (preset templates) | Fast | Medium (OpenShift) | Low (templated) | No Daemon required | Not supported (depends on builder image architecture) |
| Kaniko | Supports image layer caching, medium speed | Medium (K8s integration) | Medium | Large (K8s ecosystem) | Medium (Containerfile compatible) | No Daemon required | Not supported (requires multi-node build) |

Based on previous usage and the goal of migrating OCP image builds, we consider using Buildah for image building first, and then adding other Tasks as needed.

Buildah kernel requirements:

1. Red Hat Enterprise Linux or CentOS, version 7.4 and above. (3.10.0-693)
2. Other systems require support for OverlayFS or fuse-overlayfs filesystem.

fuse-overlayfs kernel requirements:

- libfuse > v3.2.1
- user namespace: Linux Kernel > v4.18.0

OverlayFS: Introduced in kernel version 3.18.0, improved by docker 4.0.

### Goals

1. Ability to build images through Containerfile
2. Provide default images for building
3. Provide building documentation and use cases (Docker migration to Buildah, OCP build migration to Buildah)

### Non-Goals

- Multi-architecture builds
- Default build caching

### Use Cases

- Building images
- Pushing images (skip push)
- HTTP repository builds
- Self-signed certificates
- Configuring credentials
- Setting different build formats (oci, docker)
- Supporting custom build parameters

### Requirements

- Support Containerfile image building
- Ability to push to default image registry (http/https)
- Ability to push to private image registry

## Design Details

Comparison of differences between OCP and Tekton task

**Parameters**

| Name | Description | Required | Default Value | Tekton | OCP | Alauda |
| ---- | ----------- | -------- | ------------- | ------ | --- | ------ |
| IMAGE | Target image value for building (supports multiple tags) | Yes | | ✓ | ✓ | ✓ |
| BUILDER_IMAGE | Image for executing builds | Yes | quay.io/buildah/stable:v1 | ✓ | ✗ | ✓ |
| STORAGE_DRIVER | Storage driver | Yes | overlay | ✓ | ✓ | ✓ |
| CONTAINERFILE | Containerfile path | Yes | ./Containerfile | ✓ | ✓ | ✓ |
| CONTEXT | Build context | Yes | | ✓ | ✓ | ✓ |
| TLSVERIFY | TLS verification | No | true | ✓ | ✓ | ✓ |
| FORMAT | Image format | No | oci | ✓ | ✓ | ✓ |
| BUILD_EXTRA_ARGS | Extra build parameters | No | | ✓ | ✓ | ✓ |
| PUSH_EXTRA_ARGS | Extra push parameters | No | | ✓ | ✓ | ✓ |
| SKIP_PUSH | Skip push | No | false | ✓ | ✓ | ✓ |
| BUILD_ARGS | Build arguments | No | | ✓ | ✓ | ✓ |
| PREPARE_SCRIPT | Preparation script | No | | ✗ | ✗ | ✓ |

**Workspaces**

| Name | Description | Required | Tekton | OCP | Alauda |
| ---- | ----------- | -------- | ------ | --- | ------ |
| source | Source code directory | Yes | ✓ | ✓ | ✓ |
| sslcertdir | Certificate directory | No | ✓ | ✗ | ✓ |
| registryconfig | Configuration file directory | No | ✓ | ✓ | ✓ |
| rhel-entitlement | Subscription directory | No | ✗ | ✓ | ✗ |

**Results**

| Name | Description | Required | Tekton | OCP | Alauda |
| ---- | ----------- | -------- | ------ | --- | ------ |
| image-digest | Image digest | Yes | ✓ | ✓ | ✓ |
| image-url | Image URL | Yes | ✓ | ✓ | ✓ |

**Build Runtime Images**

Tekton uses: quay.io/buildah/stable:v1
The publicly released image address for buildah, built using fedora as the base image.

OCP uses: registry.redhat.io/ubi8/buildah:8.10-12

Uses ubi8 as the base image to build the buildah image.

buildah/stable:

- Can get the latest buildah updates.
- Disadvantage: Currently, the company doesn't maintain fedora images internally. Vulnerability updates are not as timely as ubi8.

ubi8/buildah:

- Can provide better security updates

Consider using ubi8/buildah as the build runtime image.

**Task Implementation:**

```yaml
---
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: buildah
  labels:
    app.kubernetes.io/version: "0.9"
  annotations:
    tekton.dev/categories: Image Build
    tekton.dev/pipelines.minVersion: "0.50.0"
    tekton.dev/tags: image-build
    tekton.dev/platforms: "linux/amd64,linux/arm64"
    tekton.dev/displayName: buildah
spec:
  description: >-
    Buildah task builds source into a container image and
    then pushes it to a container registry.

    Buildah Task builds source into a container image using Project Atomic's
    Buildah build tool.It uses Buildah's support for building from Containerfiles,
    using its buildah bud command.This command executes the directives in the
    Containerfile to assemble a container image, then pushes that image to a
    container registry.

  params:
  - name: IMAGE
    description: Reference of the image buildah will produce.
  - name: BUILDER_IMAGE
    description: The location of the buildah builder image.
    default: quay.io/buildah/stable:v1
  - name: STORAGE_DRIVER
    description: Set buildah storage driver
    default: overlay
  - name: CONTAINERFILE
    description: Path to the Containerfile to build.
    default: ./Containerfile
  - name: CONTEXT
    description: Path to the directory to use as context.
    default: .
  - name: TLSVERIFY
    description: Verify the TLS on the registry endpoint (for push/pull to a non-TLS registry)
    default: "true"
  - name: FORMAT
    description: The format of the built container, oci or docker
    default: "oci"
  - name: BUILD_EXTRA_ARGS
    description: Extra parameters passed for the build command when building images. WARNING - must be sanitized to avoid command injection
    default: ""
  - name: PUSH_EXTRA_ARGS
    description: Extra parameters passed for the push command when pushing images. WARNING - must be sanitized to avoid command injection
    type: string
    default: ""
  - name: SKIP_PUSH
    description: Skip pushing the built image
    default: "false"
  - name: BUILD_ARGS
    description: Containerfile build arguments, array of key=value
    type: array
    default:
    - ""
  workspaces:
  - name: source
  - name: sslcertdir
    optional: true
  - name: registryconfig
    description: >-
      An optional workspace that allows providing a .docker/config.json file
      for Buildah to access the container registry.
      The file should be placed at the root of the Workspace with name config.json.
    optional: true
  results:
  - name: IMAGE_DIGEST
    description: Digest of the image just built.
  - name: IMAGE_URL
    description: Image repository where the built image would be pushed to
  steps:
  - name: build-and-push
    image: $(params.BUILDER_IMAGE)
    workingDir: $(workspaces.source.path)
    env:
    - name: PARAM_IMAGE
      value: $(params.IMAGE)
    - name: PARAM_STORAGE_DRIVER
      value: $(params.STORAGE_DRIVER)
    - name: PARAM_CONTAINERFILE
      value: $(params.CONTAINERFILE)
    - name: PARAM_CONTEXT
      value: $(params.CONTEXT)
    - name: PARAM_TLSVERIFY
      value: $(params.TLSVERIFY)
    - name: PARAM_FORMAT
      value: $(params.FORMAT)
    - name: PARAM_BUILD_EXTRA_ARGS
      value: $(params.BUILD_EXTRA_ARGS)
    - name: PARAM_PUSH_EXTRA_ARGS
      value: $(params.PUSH_EXTRA_ARGS)
    - name: PARAM_SKIP_PUSH
      value: $(params.SKIP_PUSH)
    args:
    - $(params.BUILD_ARGS[*])
    script: |
        1. prepare build params.
        2. execute buildah build command.
        3. execute buildah push command.
        4. save image digest and image url to result.
    volumeMounts:
    - name: varlibcontainers
      mountPath: /var/lib/containers
    securityContext:
      privileged: true
  volumes:
  - name: varlibcontainers
    emptyDir: {}
```

### Performance

- No daemon required, high performance.
- When building heterogeneous images, QEMU support is required.

### Risks and Mitigation Measures

When using the overlay storage driver, privileged mode is required. vfs can support more systems with only SETFCAP permissions.

Test results when using SETFCAP/privileged permissions with vfs:

| vfs | ubuntu:22.04 5.4.0-135-generic | 5.15.0-56-generic | 3.10.0-1160.el7.x86_64| 4.19.90-24.4.v2101.ky10.aarch64| 4.18.0-80.el8.x86_64|
|---|---|---|---|---|---|
| SETFCAP permissions | ❌ | ✅ | ❌ | ✅ | ✅ |
| privileged| ✅ | ✅ | ✅ | ✅ | ✅ |

Test results when using SETFCAP/privileged permissions with overlay:

| overlay | ubuntu:22.04 5.4.0-135-generic | 5.15.0-56-generic| 3.10.0-1160.el7.x86_64| 4.19.90-24.4.v2101.ky10.aarch64|4.18.0-80.el8.x86_64|
|---|---|---|---|---|---|
| SETFCAP permissions | ❌ | ✅ | ❌ | ❌ | ❌ |
| privileged | ✅ | ✅ | ✅ | ✅ | ✅ |

If support for running on 3.10.0-1160.el7.x86_64 is needed, the existing task's SETFCAP mode needs to be changed to privileged permissions.

To ensure security, the vfs storage driver is used by default with SETFCAP permissions.

### Test Plan

1. Integration Tests

- Building images
- Pushing images (skip push)
- HTTP repository builds
- Self-signed certificates
- Configuring credentials
- Setting different build formats (oci, docker)
- Supporting custom build parameters
- Testing if built images run as expected

### Infrastructure Needed

1. CI/CD environment
2. Registry for publishing images

## References

- [Tekton Buildah Task](https://hub.tekton.dev/tekton/task/buildah)
- [Buildah System Requirements](https://github.com/containers/buildah/blob/main/install.md#system-requirements)
- [OCP Buildah Task](https://github.com/openshift-pipelines/tektoncd-catalog/tree/p/tasks/task-buildah/0.6.0)
- [OCP Buildah Dockerfile](https://catalog.redhat.com/software/containers/ubi8/buildah/602686f7b16b1eb2e30807ee?container-tabs=dockerfile)
- [Buildah Containerfile](https://github.com/containers/image_build/blob/main/buildah/Containerfile)
- [OCP Task Repository](https://github.com/openshift-pipelines/task-containers)
- [Buildah Build Documentation](https://github.com/containers/buildah/blob/main/docs/buildah-build.1.md)
- [Alauda Version Baseline](https://confluence.alauda.cn/pages/viewpage.action?pageId=264110543#v4.0.0%E7%89%88%E6%9C%AC%E5%9F%BA%E7%BA%BF-%E6%93%8D%E4%BD%9C%E7%B3%BB%E7%BB%9F%E5%8F%8ACPU%E5%9E%8B%E5%8F%B7)
- [Ningsi Buildah Issues](https://confluence.alauda.cn/pages/viewpage.action?pageId=130576555)
