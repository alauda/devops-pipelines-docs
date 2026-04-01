---
weight: 20
status: proposed
title: Maven Task
creation-date: "2025-02-12"
category: task
authors:
  - "@danielfbm"
---

# TEP-0001: Maven Task

<!-- toc -->
- [Summary](#summary)
- [Motivation](#motivation)
  - [Goals](#goals)
  - [Non-Goals](#non-goals)
  - [Use Cases](#use-cases)
  - [Requirements](#requirements)
- [Proposal](#proposal)
  - [Notes and Caveats](#notes-and-caveats)
- [Design Details](#design-details)
- [Design Evaluation](#design-evaluation)
  - [Reusability](#reusability)
  - [Simplicity](#simplicity)
  - [Flexibility](#flexibility)
  - [Conformance](#conformance)
  - [User Experience](#user-experience)
  - [Performance](#performance)
  - [Risks and Mitigations](#risks-and-mitigations)
  - [Drawbacks](#drawbacks)
- [Alternatives](#alternatives)
- [Implementation Plan](#implementation-plan)
  - [Test Plan](#test-plan)
  - [Infrastructure Needed](#infrastructure-needed)
  - [Upgrade and Migration Strategy](#upgrade-and-migration-strategy)
  - [Implementation Pull Requests](#implementation-pull-requests)
- [References](#references)
<!-- /toc -->

## Summary {#summary}

This proposal aims to create a unified Maven Task for executing Maven build, test, and deployment operations in Tekton Pipelines. The Task will integrate best practices from existing Maven Tasks in OpenShift Pipeline and Tekton Hub, while ensuring existing users can migrate to the new Task with zero or minimal cost. The new Task will provide secure default configurations and flexible customization options to meet the needs of different users.

## Motivation {#motivation}

Currently, there are multiple Maven Task implementations in the Tekton ecosystem (primarily OpenShift Pipeline and Tekton Hub), which leads to the following issues:

1. Users face confusion when choosing Tasks
2. Maintaining multiple implementations increases community burden
3. Functional differences between implementations make migration difficult
4. Inconsistent implementation of security and best practices

By providing a unified Maven Task, we can address these issues and provide users with a better experience.

### Goals {#goals}

1. Provide a fully functional Maven Task that supports common Maven usage scenarios
2. Ensure zero-cost migration from existing OpenShift Pipeline Maven Task
3. Provide a simple migration path from Tekton Hub Maven Task
4. Provide secure default Maven images while supporting custom build environments
5. Optimize build performance and resource usage
6. Provide clear documentation and migration guides

### Non-Goals {#non-goals}

1. Replace project-specific Maven configurations or build logic
2. Provide complex build optimization strategies
3. Implement build functionality unrelated to Maven

### Use Cases {#use-cases}

1. **Java Application Building**
   - Compile source code
   - Run unit tests
   - Package applications

2. **Dependency Management**
   - Update dependency versions
   - Handle private repository authentication
   - Configure mirror repositories

3. **Deployment Operations**
   - Deploy to Maven repositories
   - Execute environment-specific deployments
   - Run integration tests

4. **Custom Build Environments**
   - Use specific JDK versions
   - Configure custom Maven settings
   - Use private build toolchains

### Requirements {#requirements}

1. **Functional Requirements**
   - Support all standard Maven lifecycle goals
   - Support custom Maven settings and configurations
   - Support proxy server configurations
   - Support private repository authentication

2. **Performance Requirements**
   - Support Maven local repository caching
   - Optimize build times
   - Minimize resource usage

3. **Security Requirements**
   - Provide security-scanned base images
   - Securely handle sensitive information
   - Support principle of least privilege

4. **Compatibility Requirements**
   - Fully compatible with OpenShift Pipeline Maven Task configurations
   - Support main features of Tekton Hub Maven Task
   - Backward compatible with existing Pipeline definitions

## Proposal {#proposal}

Create a new unified Maven Task with the following characteristics:

1. **Workspace Design**
   - Maintain the same workspace structure as OpenShift Pipeline
   - Add optional maven-local-repo workspace
   - Support custom Maven settings

2. **Parameter Design**
   - Support two authentication methods (workspace and parameters)
   - Provide default secure Maven images
   - Flexible build goal configurations

3. **Security Features**
   - Secure default configurations
   - Secure handling of sensitive information
   - Least privilege execution

### Notes and Caveats {#notes-and-caveats}

1. Default to UBI base images to ensure security
2. Recommend using workspace approach for handling sensitive information
3. Local repository caching may increase storage usage

## Design Details {#design-details}

### Task Comparison

To help users understand differences and migration paths, here's a detailed comparison of three Task implementations:

#### Workspace Comparison

| Workspace Name | OpenShift Pipeline | Tekton Hub | New Unified Task | Description |
|----------------|-------------------|------------|------------------|-------------|
| source | ✓ | ✓ | ✓ | Maven project source directory |
| maven-settings | ✓ (optional) | ✓ | ✓ (optional) | Custom Maven configuration file |
| server_secret | ✓ (optional) | ✗ | ✓ (optional) | Server authentication information |
| proxy_secret | ✓ (optional) | ✗ | ✓ (optional) | Proxy server authentication information |
| proxy_configmap | ✓ (optional) | ✗ | ✓ (optional) | Proxy server configuration information |
| maven-local-repo | ✗ | ✓ (optional) | ✓ (optional) | Maven local repository |

#### Parameter Comparison

| Parameter Name | OpenShift Pipeline | Tekton Hub | New Unified Task | Description |
|----------------|-------------------|------------|------------------|-------------|
| GOALS | ✓ | ✓ | ✓ | Maven build goals |
| MAVEN_MIRROR_URL | ✓ | ✓ | ✓ | Maven repository mirror URL |
| SUBDIRECTORY/CONTEXT_DIR | ✓ | ✓ | ✓ | Project subdirectory, using Openshift parameter name |
| MAVEN_IMAGE | ✗ | ✓ | ✓ | Maven base image |
| Server authentication parameters | via workspace | via parameters | via workspace | Maintain compatibility with Openshift |
| Proxy server parameters | via workspace | via parameters | via workspace | Maintain compatibility with Openshift |

### Task Specification

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: maven
  labels:
    app.kubernetes.io/version: "0.5.0"
  annotations:
    tekton.dev/pipelines.minVersion: "0.56.0"
    tekton.dev/categories: Build Tools
    tekton.dev/tags: build-tool
    tekton.dev/platforms: "linux/amd64,linux/arm64"
spec:
  description: >-
    This Task can be used to run Maven builds, tests, and deployments.
    It supports workspace-based configuration for compatibility with existing implementations.

  workspaces:
    - name: source
      description: The workspace containing maven project
    - name: maven-settings
      description: The workspace containing custom maven settings
      optional: true
    - name: server_secret
      description: The workspace containing server credentials
      optional: true
    - name: proxy_secret
      description: The workspace containing proxy credentials
      optional: true
    - name: proxy_configmap
      description: The workspace containing proxy configuration
      optional: true
    - name: maven-local-repo
      description: The workspace for Maven local repository
      optional: true

  params:
    - name: MAVEN_IMAGE
      type: string
      description: Maven base image
      default: registry.access.redhat.com/ubi8/openjdk-11:latest
    - name: GOALS
      description: Maven goals to run
      type: array
      default: ["package"]
    - name: MAVEN_MIRROR_URL
      description: Maven repository mirror URL
      type: string
      default: ""
    - name: SUBDIRECTORY
      description: The context directory for Maven project
      type: string
      default: "."

  results:
    - name: group-id
      description: Maven project group ID
    - name: artifact-id
      description: Maven project artifact ID
    - name: version
      description: Maven project version

  steps:
    - name: generate-settings
      image: registry.access.redhat.com/ubi8/ubi-minimal:8.9
      script: |
        #!/usr/bin/env bash
        # Settings generation logic here
        # 1. Check for existing settings
        # 2. Generate new settings if needed
        # 3. Configure authentication (prioritize object parameters)
        # 4. Configure proxy (prioritize object parameters)
        # 5. Configure mirror

    - name: maven
      image: $(params.MAVEN_IMAGE)
      workingDir: $(workspaces.source.path)/$(params.CONTEXT_DIR)
      script: |
        #!/usr/bin/env bash
        # 1. Set up environment
        # 2. Execute Maven goals and store results
        # 3. Extract and store results
```

## Design Evaluation {#design-evaluation}

### Reusability {#reusability}

- Support all standard Maven usage scenarios
- Provide flexible configuration options
- Can be used in different environments

### Simplicity {#simplicity}

- Keep configuration interface simple and clear
- Provide reasonable default values
- Clear documentation and examples

### Flexibility {#flexibility}

- Support custom Maven images
- Support multiple authentication methods
- Extensible parameter design

### Conformance {#conformance}

- Compatible with existing OpenShift Pipeline Tasks
- Not fully compatible with Tekton Hub existing Tasks, but easy to migrate
- Follow Tekton best practices
- Unified configuration patterns

### User Experience {#user-experience}

- Zero-cost migration path
- Clear error messages
- Detailed usage documentation

### Performance {#performance}

- Support local repository caching
- Optimized build processes
- Resource usage optimization

### Risks and Mitigations {#risks-and-mitigations}

1. **Migration Risks**
   - Provide detailed migration guides
   - Maintain full compatibility
   - Provide rollback mechanisms

2. **Security Risks**
   - Regularly update base images
   - Secure default configurations
   - Principle of least privilege
   - Image vulnerability risks

#### Image Handling

Consider using chainguard images https://images.chainguard.dev/directory/images/maven/overview

Default to latest LTS version (referencing Adoptium https://adoptium.net/temurin/releases/)

- `Maven 3.9.9 - OpenJDK 21`

### Drawbacks {#drawbacks}

1. Increased configuration complexity to support compatibility
2. Need to maintain multiple authentication methods
3. May require more storage space

## Alternatives {#alternatives}

At this stage, there are no better alternatives than a unified Maven Task that keeps compatibility while improving security defaults and usability.

## Implementation Plan {#implementation-plan}

### Test Plan {#test-plan}

1. **Integration Tests**
   - Provide Maven program validation task functionality, including:
     - Dependency pulling
     - Build, unit tests, integration tests
     - Artifact distribution
   - Maven repository capability tests:
     - Central mirror dependency mirroring
     - Private Maven repository dependency pulling
     - Private Maven repository distribution
     - TODO: Group repository usage for connecting multiple Nexus repositories
   - Local caching capability tests

2. **Compatibility Tests**
   - OpenShift Pipeline migration tests
   - Version compatibility tests

### Infrastructure Needed {#infrastructure-needed}

1. CI/CD environment
2. Test Maven repositories

### Upgrade and Migration Strategy {#upgrade-and-migration-strategy}

1. **OpenShift Pipeline Users**
   - Directly replace Task references
   - Maintain existing configurations
   - No other changes required

2. **Tekton Hub Users**
   - Update Task references
   - Adjust authentication configurations

### Implementation Pull Requests {#implementation-pull-requests}

1. Task implementation and integration test PR
2. Documentation and examples PR

## References {#references}

1. [OpenShift Pipeline Maven Task](https://github.com/openshift-pipelines/task-maven)
2. [Tekton Hub Maven Task](https://github.com/tektoncd/catalog/tree/main/task/maven)
3. [Maven Best Practices](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
4. [ChainGuard maven](https://images.chainguard.dev/directory/images/maven/overview)
5. [Adoptium maven](https://adoptium.net/temurin/releases/)

<a id="alternatives"></a>
