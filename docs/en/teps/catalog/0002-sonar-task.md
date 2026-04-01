---
status: WIP
title: Sonar Task
creation-date: "2025-02-19"
category: task
authors:
  - "@mingfu"
---

# TEP-0002: Sonar Task

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

This proposal aims to create a unified Sonar Task for performing code static analysis, security scanning, and other operations in Tekton Pipelines. The Task is based on best practices from the existing Tekton Hub Sonar Task while ensuring that existing users can migrate to the new Task at zero or minimal cost. The new Task will provide secure default configurations and flexible customization options to meet the needs of different users.

## Motivation {#motivation}

By providing a unified Sonar Task, we ensure compatibility, security, and flexibility while delivering a better user experience.

### Goals {#goals}

1. Provide a fully functional Sonar Task that supports common Sonar usage scenarios
2. Ensure no temporary files are left in the workspace after scanning
3. Provide a simple migration path from Tekton Hub Sonar Task
4. Provide secure default Sonar images while supporting custom build environments
5. Optimize build performance and resource usage
6. Provide clear documentation and migration guides

### Non-Goals {#non-goals}

1. Replace project-specific Sonar configurations or build logic
2. Provide complex quality gate strategies

### Use Cases {#use-cases}

1. **Scanning different revision code**
   - Main branch
   - Non-main branches
   - Pull Request

2. **Scanning code in different languages**
   - Java
   - Go

3. **Custom build environments**
   - Using images containing specific versions of sonar scanner
   - Configuring custom scan configurations

### Requirements {#requirements}

1. **Functional Requirements**
   - Support scanning code in multiple languages
   - Support scanning code on different revisions
   - Support custom Sonar settings and configurations

2. **Performance Requirements**
   - Optimize scan time
   - Minimize resource usage

3. **Security Requirements**
   - Provide security-scanned base images
   - Securely handle sensitive information
   - Support principle of least privilege

4. **Compatibility Requirements**
   - Support main features of Tekton Hub Sonar Task
   - Backward compatibility with existing Pipeline definitions

## Proposal {#proposal}

Create a new unified Sonar Task with the following characteristics:

1. **Workspace Design**
   - Maintain the same workspace structure as Tekton Hub Sonar Task

2. **Parameter Design**
   - Preserve existing parameters from Tekton Hub Sonar Task for compatibility
   - Add SONAR_FLAGS parameter to support user-defined sonar scanner parameters

3. **Security Features**
   - Secure default configurations
   - Secure handling of sensitive information
   - Least privilege execution

### Notes and Caveats {#notes-and-caveats}

1. Use UBI base images by default to ensure security
2. Recommend using workspace approach for handling sensitive information
3. Local repository caching may increase storage usage

## Design Details {#design-details}

### Task Comparison

To help users understand the differences and migration path, here's a detailed comparison of the two Task implementations:

#### Workspaces Comparison

| Workspace Name     | Tekton Hub | New Unified Task | Description                    |
| ------------------ | ---------- | ---------------- | ------------------------------ |
| source             | ✓          | ✓                | Project source code directory  |
| sonar-settings     | ✓ (optional) | ✓ (optional)  | Custom Sonar configuration file |
| sonar-credentials  | ✓ (optional) | ✓ (optional)  | Server authentication information |

#### Parameters Comparison

| Parameter Name           | Tekton Hub | New Unified Task | Description                                                                         |
| ------------------------ | ---------- | ---------------- | ----------------------------------------------------------------------------------- |
| SONAR_HOST_URL           | ✓          | ✓                | Sonar server URL (sonar.host.url)                                                   |
| SONAR_PROJECT_KEY        | ✓          | ✓                | Sonar project unique identifier (sonar.projectKey)                                  |
| SONAR_BRANCH_NAME        | ✓          | ✓                | Revision information of scanned source code (sonar.branch.name)                     |
| PROJECT_VERSION          | ✓          | ✓                | Version information of scanned source code (sonar.projectVersion)                   |
| SOURCE_TO_SCAN           | ✓          | ✓                | Source code path (sonar.sources)                                                    |
| SONAR_ORGANIZATION       | ✓          | ✓                | Sonar organization name, applicable for sonar cloud scenarios (sonar.organization) |
| SONAR_SCANNER_IMAGE      | ✓          | ✓                | Image used for executing scans                                                      |
| PROPERTIES_CREATE_IMAGE  | ✓          | ✓                | Image used for preparing sonar configuration files                                  |
| SONAR_LOGIN_KEY          | ✓          | ✓                | Key name for storing token information in sonar-credentials workspace (sonar.login) |
| SONAR_PASSWORD_KEY       | ✓          | ✓                | Key name for storing password information in sonar-credentials workspace (sonar.password) |
| SONAR_TOKEN_KEY          |            | ✓                | Key name for storing token information in sonar-credentials workspace (sonar.token) |
| SONAR_PROPERTIES         |            | ✓                | Other custom parameters                                                             |

:::warning Sonar Authentication Methods

Before version 2025.1A, two authentication methods were supported:
1. Username (sonar.login) and password (sonar.password)
2. Token (sonar.login)

Sonar version 2025.1A [deprecated sonar.login and sonar.password](https://docs.sonarsource.com/sonarqube-server/latest/analyzing-source-code/analysis-parameters/#authentication-to-the-server) and changed to use `sonar.token` for passing credentials.
:::

#### Configuration Priority Comparison

Priority from high to low:

| Configuration Method                    | Tekton Hub | New Unified Task | Description                                                                   |
| --------------------------------------- | ---------- | ---------------- | ----------------------------------------------------------------------------- |
| Built-in properties                     |            | ✓                | Task built-in configuration                                                   |
| Source code sonar-project.properties    | ✓          | ✓                |                                                                               |
| sonar-settings workspace                | ✓          | ✓                | Community implementation **overwrites** source code config files, new unified task **merges** |
| Task parameters                         | ✓          | ✓                |                                                                               |
| Task SONAR_PROPERTIES parameter         |            | ✓                |                                                                               |

Built-in configurations include:

1. sonar.sourceEncoding=UTF-8
2. sonar.sources=.
3. sonar.qualitygate.timeout=7200

#### Results

| Result Name      | Tekton Hub | New Unified Task | Description        |
| ---------------- | ---------- | ---------------- | ------------------ |
| SCAN_RESULT_URL  |            | ✓                | URL of scan results |

### Task Specification

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: sonarqube-scanner
  labels:
    app.kubernetes.io/version: "0.5"
  annotations:
    tekton.dev/deprecated: "true"
    tekton.dev/pipelines.minVersion: "0.17.0"
    tekton.dev/categories: Security
    tekton.dev/tags: security
    tekton.dev/displayName: "sonarqube scanner"
    tekton.dev/platforms: "linux/amd64,linux/arm64"
spec:
  description: >-
    The following task can be used to perform static analysis on the source code
    provided the SonarQube server is hosted

    SonarQube is the leading tool for continuously inspecting the Code Quality and Security
    of your codebases, all while empowering development teams. Analyze over 25 popular
    programming languages including C#, VB.Net, JavaScript, TypeScript and C++. It detects
    bugs, vulnerabilities and code smells across project branches and pull requests.

  workspaces:
    - name: source
      description: "Workspace containing the code which needs to be scanned by SonarQube"
    - name: sonar-settings
      description: "Optional workspace where SonarQube properties can be mounted"
      optional: true
    - name: sonar-credentials
      description: |
        A workspace containing a login or password for use within sonarqube.
      optional: true

  params:
    ... # Existing Tekton Hub Task parameters
    - name: SONAR_FLAGS
      description: Custom scan parameters with the highest priority, formatted as `key=value`.
      type: array
      default: |
        - sonar.qualitygate.wait

  results:
    - name: SCAN_RESULT_URL
      description: The URL of the SonarQube scan result

  steps:
    - name: sonar-properties-create
      image: registry.access.redhat.com/ubi8/ubi-minimal:8.9
      script: |
        #!/usr/bin/env bash
        # 1. Maintain same logic as Tekton Hub Task
        # 2. Parse SONAR_FLAGS parameters
        # 3. Save configuration file in .git/sonar-project.properties to avoid polluting workspace

    - name: maven
      image: $(params.MAVEN_IMAGE)
      workingDir: $(workspaces.source.path)/$(params.CONTEXT_DIR)
      script: |
        #!/usr/bin/env bash
        # 1. Parse parameters, generate command line arguments
        #    - `sonar.qualitygate.wait`
        #    - `sonar.working.directory`
        #    - `project.settings`
        # 2. Execute scan using sonar-scanner
        # 3. Clean up temporary files
```

## Design Evaluation {#design-evaluation}

### Reusability {#reusability}

- Supports all standard Sonar usage scenarios
- Provides flexible configuration options
- Can be used in different environments

### Simplicity {#simplicity}

- Maintains simple and clear configuration interface
- Provides reasonable default values
- Clear documentation and examples

### Flexibility {#flexibility}

- Supports custom Sonar images
- Supports multiple authentication methods
- Extensible parameter design

### Conformance {#conformance}

- Fully compatible with Tekton Hub
- Follows Tekton best practices
- Unified configuration patterns

### User Experience {#user-experience}

- Zero-cost migration path
- Clear error messages
- Detailed usage documentation

### Performance {#performance}

- Supports local repository caching
- Optimized build process
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

### Image Handling

Directly use officially provided images.

- https://github.com/SonarSource/sonar-scanner-cli-docker/blob/master/Dockerfile
- https://hub.docker.com/r/sonarsource/sonar-scanner-cli/tags

### Drawbacks {#drawbacks}

1. Increased configuration complexity to support compatibility
2. Need to maintain multiple authentication methods

## Alternatives {#alternatives}

At this stage, there are no better alternatives than a unified Sonar Task that preserves compatibility and improves secure defaults.

## Implementation Plan {#implementation-plan}

### Test Plan {#test-plan}

1. **Integration Tests**
   - Provide different revision code scanning capability tests
     - Main branch
     - Non-main branches
     - PR
   - Provide different language scanning tests (verify sonar analysis results, such as coverage, etc.)
     - Java
     - Go
     - Other languages
   - Quality gate tests
     - Pass quality gate
     - Fail quality gate

2. **Compatibility Tests**
   - Migration tests with Tekton Hub

### Infrastructure Needed {#infrastructure-needed}

1. CI/CD environment
2. Sonar Server

### Upgrade and Migration Strategy {#upgrade-and-migration-strategy}

1. **Tekton Hub Users**
   - Update Task references

### Implementation Pull Requests {#implementation-pull-requests}

1. Task implementation and integration test PR
2. Documentation and examples PR

## References {#references}

1. [Sonar Analysis Parameters](https://docs.sonarsource.com/sonarqube-server/latest/analyzing-source-code/analysis-parameters)
2. [Tekton Hub Sonar Task](https://github.com/tektoncd/catalog/tree/main/task/sonarqube-scanner)
3. [Sonar Scanner Image](https://hub.docker.com/r/sonarsource/sonar-scanner-cli/tags)

<a id="alternatives"></a>
