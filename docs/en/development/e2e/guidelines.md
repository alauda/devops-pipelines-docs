---
title: E2E Test Writing Guidelines
weight: 10
---

# E2E Test Writing Guidelines

This document provides guidelines and best practices for writing end-to-end (E2E) tests for the TektonCD Operator.

## Overview

E2E tests are designed to validate the complete functionality of the TektonCD Operator in a real Kubernetes environment. These tests ensure that all components work together correctly and that the system behaves as expected from an end-user perspective.

The test suite uses **Behavior-Driven Development (BDD)** methodology with the following technologies:

- **Framework**: [godog](https://github.com/cucumber/godog) (Cucumber for Go)
- **BDD Library**: [AlaudaDevops/bdd](https://github.com/AlaudaDevops/bdd)
- **Language**: Gherkin syntax with Chinese (zh-CN)
- **Reporting**: Allure reports

## Directory Structure

The E2E test suite is organized in the `testing/` directory:

```
testing/
├── features/          # Feature files (Gherkin scenarios)
│   ├── *.feature     # Test scenarios in Chinese
│   └── testdata/     # Test data and resource files
├── steps/            # Step definitions (Go implementations)
├── scripts/          # Helper scripts for test setup
├── config/           # Configuration files
│   ├── config.yaml   # Main configuration file
│   └── *.yaml        # Template files
├── main_test.go      # Test entry point
├── Makefile          # Test execution commands
└── go.mod            # Go module dependencies
```

## Test Organization

### Feature File Naming

Feature files should follow this naming convention:

```
<component>.<feature-area>.feature
```

Examples:
- `pipeline.base.feature` - Basic pipeline functionality
- `pipeline.maven.feature` - Maven-specific pipeline tests
- `triggers.feature` - Trigger functionality
- `enhancement.feature` - Enhancement features

### Feature File Structure

Every feature file must follow this structure:

```gherkin
# language: zh-CN

@tag1
@tag2
@e2e
功能: <Feature Name>

    作为一名<Role>
    我希望能够<Action>
    以便<Benefit>

    背景:
        假定 <Common preconditions>
        并且 <More preconditions>

    @scenario-tag
    场景: <Scenario Description>
        假如 <Given step>
        当 <When step>
        那么 <Then step>
        并且 <And step>

    @scenario-outline-tag
    场景大纲: <Scenario Outline Description> - <parameter>
        假如 <Given step with <parameter>>
        当 <When step>
        那么 <Then step>

        例子:
            | parameter | expected |
            | value1    | result1  |
            | value2    | result2  |
```

## Tagging Strategy

Tags are used to organize, filter, and control test execution. Follow these conventions:

### Required Tags

Every feature file must include:

```gherkin
@e2e                    # Marks this as an E2E test
@tektoncd-operator      # Component being tested
```

### Component Tags

Use component-specific tags to identify which part of the system is being tested:

- `@tektoncd-pipeline` - Tekton Pipeline component
- `@tektoncd-triggers` - Tekton Triggers component
- `@tektoncd-chains` - Tekton Chains component
- `@tektoncd-results` - Tekton Results component
- `@tektoncd-enhancement` - Enhancement features
- `@hubs-wrapper` - Hubs wrapper functionality
- `@pac` - Pipeline as Code

### Test Type Tags

Classify tests by their type:

- `@smoke` - Critical functionality tests (must pass)
- `@api` - API-level tests
- `@ui` - User interface tests
- `@manual` - Tests requiring manual execution
- `@automated` - Fully automated tests

### Execution Control Tags

Control how tests are executed:

- `@prepare` - Preparation tests run before upgrades
- `@upgrade` - Upgrade scenario tests
- `@skip-cleanup-namespace` - Prevents namespace cleanup after test
- `@buildah-compatible` - Tests that require buildah

### Scenario Identification Tags

Each scenario should have a unique identifier tag:

```gherkin
@tektoncd-pipeline-basic-001
@tektoncd-triggers-git-event-001
```

Format: `@<component>-<feature-area>-<sequence-number>`

### Tag Filtering in Tests

The Makefile defines tag expressions for different test runs:

**Serial Tests** (require sequential execution):
```makefile
@tektoncd-enhancement,tektoncd-results && ~@automatable && ~@manual && ~@ui
```

**Parallel Tests** (can run concurrently):
```makefile
~@tekton-config-uninstall && ~@tektoncd-results && ~@tektoncd-enhancement && ~@automatable && ~@manual && ~@ui
```

## Writing Feature Files

### Language and Format

1. **Language Declaration**
   ```gherkin
   # language: zh-CN
   ```
   This must be the first line of every feature file.

2. **User Story Format**
   ```gherkin
   功能: <Feature Name>

       作为一名<Role>
       我希望能够<Action>
       以便<Benefit>
   ```

### Background (背景)

Use Background for steps that are common to all scenarios in a feature:

```gherkin
背景:
    假定 我是一名管理员用户
    并且 Tekton Operator 组件已就绪
    并且 Tekton Pipeline 组件已就绪
    并且 命名空间 "testing-pipeline-<template.{{randNumeric 6}}>" 已存在
```

### Scenarios (场景)

Simple scenarios for single test cases:

```gherkin
@smoke
@api
@tektoncd-pipeline-basic-001
场景: 创建&更新&删除 Pipeline 流水线-YAML
    假如 我是一个已登录的用户
    当 创建 "Pipeline" 资源
        """
        yaml: ./testdata/pipeline/pipeline-base.yaml
        """
    那么 资源导入结果检查通过
        | path    | value |
        | $.error | false |
```

### Scenario Outlines (场景大纲)

Use scenario outlines for data-driven tests:

```gherkin
@tektoncd-pipeline-basic-002
场景大纲: 执行&删除 Pipeline 流水线 - <result> -YAML
    当 创建 "PipelineRun" 资源
        """
        yamls:
          - ./testdata/pipeline/pipeline-status.yaml
          - ./testdata/pipeline/<pr-yaml>
        """
    那么 PipelineRun "<pr-name>" 执行<result>

    例子:
        | pr-name    | pr-yaml         | result |
        | pr-success | pr-success.yaml | 成功   |
        | pr-failed  | pr-failed.yaml  | 失败   |
```

## Test Design Principles

When writing E2E tests, follow these core principles to ensure tests are maintainable, portable, and reusable across different environments.

### Principle 1: Prefer Built-in Steps Over Custom Scripts

**Guideline**: Always use the BDD framework's built-in steps when possible. Avoid creating complex shell scripts to accomplish tasks that can be achieved with existing steps.

**Rationale**:
- Built-in steps are well-tested and maintained by the framework
- Improves test readability and maintainability
- Reduces code duplication across test scenarios
- Makes tests easier to understand for new team members
- Keeps Kubernetes test data aligned with the BDD context, including cleanup-related labels such as `testing.suite-name`

**Example**:

✅ **Good** - Using built-in steps:
```gherkin
当 创建 "Pipeline" 资源
    """
    yaml: ./testdata/pipeline/pipeline-base.yaml
    """
那么 "Pipeline" 资源检查通过
    | apiVersion    | name     | path            | value    | interval | timeout |
    | tekton.dev/v1 | pipeline | $.metadata.name | pipeline | 5s       | 30s     |
```

❌ **Bad** - Using scripts for operations that have built-in steps:
```gherkin
# Don't do this - using scripts to create and verify resources
当 执行 "创建 Pipeline 资源" 脚本成功
    | command                                                           |
    | bash -c "kubectl apply -f ./testdata/pipeline/pipeline-base.yaml" |

那么 执行 "检查 Pipeline 参数值" 脚本成功
    | command                                                                                             |
    | bash ./scripts/verify-pipeline-param.sh --name pipeline --param-name tips --expected "Hello World!" |
```

This approach has several problems:
- Hard to read and understand what's being tested
- Requires maintaining separate verification scripts for simple checks
- No reusability - each resource type needs its own script
- Poor error messages when assertions fail
- Bypasses framework's built-in retry and timeout mechanisms
- Harder to debug when tests fail
- Resources created by ad-hoc scripts do not automatically inherit `testing.suite-name=<suite-name>` and related context labels, which makes unified residue cleanup harder

**When to use custom scripts**:
- Only when functionality is not available in built-in steps
- For complex setup operations (e.g., initializing git repositories, configuring webhooks)
- For integration with external systems
- For specialized verification logic that requires custom tools

When the goal is to prepare Kubernetes resources, prefer built-in resource and namespace steps over shell scripts whenever possible.

**Resources**:
- See [AlaudaDevops BDD Documentation](https://github.com/AlaudaDevops/bdd) for complete list of built-in steps
- Check existing test scenarios for step usage examples

### Principle 2: Never Hard-code Internal Network Addresses

**Guideline**: Never hard-code internal network addresses, registry URLs, or service endpoints in test resources or scripts. Always use configuration templates to reference these values.

**Rationale**:
- Tests may run in different environments (internal network, air-gapped, cloud)
- Hard-coded addresses fail in environments without access to internal services
- Configuration-based approach enables tests to run in isolated environments like MicroOS
- Improves test portability and maintainability

**Example**:

✅ **Good** - Using configuration templates:
```yaml
apiVersion: tekton.dev/v1
kind: TaskRun
metadata:
  name: build-image
spec:
  taskSpec:
    steps:
      - name: build
        image: <config.{{.registry.test}}>/ops/buildah:latest
        script: |
          buildah push <config.{{.registry.test}}>/myapp:latest
```

❌ **Bad** - Hard-coding internal addresses:
```yaml
apiVersion: tekton.dev/v1
kind: TaskRun
metadata:
  name: build-image
spec:
  taskSpec:
    steps:
      - name: build
        image: registry.alauda.cn:60070/ops/buildah:latest
        script: |
          buildah push registry.alauda.cn:60070/myapp:latest
```

**Common configuration templates**:
- `<config.{{.registry.test}}>` - Test image registry
- `<config.{{.toolchains.gitlab.endpoint}}>` - GitLab server endpoint
- `<config.{{.toolchains.harbor.endpoint}}>` - Harbor registry endpoint
- `<config.{{.toolchains.nexus.endpoint}}>` - Nexus repository endpoint

**Configuration file structure**:
```yaml
# config.yaml
registry:
  test: registry.example.io:5000

toolchains:
  gitlab:
    endpoint: https://gitlab.example.io
  harbor:
    endpoint: https://harbor.example.io
```

### Principle 3: Design for Maximum Compatibility

**Guideline**: Write test data and configurations to be compatible with as many environments as possible, without compromising the test objective.

**Rationale**:
- Tests should work in diverse environments (self-signed certificates, HTTP registries, air-gapped networks)
- Reduces environment-specific test failures
- Improves test coverage across different deployment scenarios
- Minimizes test maintenance burden

**Example**:

✅ **Good** - Environment-agnostic configuration:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: registry-credentials
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: <config.{{.toolchains.harbor.registryConfig}}>
---
apiVersion: tekton.dev/v1
kind: TaskRun
metadata:
  name: push-image
spec:
  taskSpec:
    steps:
      - name: push
        image: <config.{{.registry.test}}>/ops/buildah:latest
        script: |
          # Use insecure flag for HTTP registries or self-signed certificates
          buildah push \
            --tls-verify=false \
            <config.{{.registry.test}}>/myapp:latest
```

❌ **Bad** - Assumes specific environment:
```yaml
apiVersion: tekton.dev/v1
kind: TaskRun
metadata:
  name: push-image
spec:
  taskSpec:
    steps:
      - name: push
        image: registry.company.internal/ops/buildah:latest
        script: |
          # Assumes HTTPS with valid certificates
          buildah push registry.company.internal/myapp:latest
```

**Compatibility considerations**:

1. **Registry Access**:
   - Support both HTTP and HTTPS registries
   - Handle self-signed certificates gracefully
   - Use `--tls-verify=false` or similar flags when security is not the test focus

2. **Network Connectivity**:
   - Don't assume internet access
   - Use configurable mirrors for public repositories
   - Support air-gapped environments

3. **Authentication**:
   - Use configurable credentials via `config.yaml`
   - Support multiple authentication methods
   - Provide example configurations for different setups

4. **Resource Constraints**:
   - Specify reasonable resource limits that work on minimal clusters
   - Don't assume unlimited resources
   - Use small test images when possible

**When to make exceptions**:
- When testing specific security features (e.g., TLS verification)
- When the test explicitly validates environment-specific behavior
- Document such requirements in test description and tags

### Principle 4: Maintain Clear Separation of Concerns

**Guideline**: Keep test scenarios focused on a single functional area. Separate test logic, test data, and test configuration.

**Structure**:
```
features/
├── pipeline.base.feature      # Pipeline core functionality
├── pipeline.maven.feature     # Maven-specific tests
├── triggers.feature           # Trigger functionality
└── testdata/
    ├── pipeline/              # Pipeline test data
    ├── triggers/              # Trigger test data
    └── shared/                # Shared test resources
```

**Benefits**:
- Easier to locate and update tests
- Reduces test interdependencies
- Simplifies test maintenance
- Improves test execution parallelism

### Principle 5: Always Specify Resource Limits for Pods

**Guideline**: All Pod specifications in test resources must explicitly define CPU and memory resource requests and limits. Never rely on cluster default values.

**Rationale**:
- Different Kubernetes environments may have different default resource settings
- Prevents Out-of-Memory (OOM) kills in resource-constrained environments
- Ensures test stability and predictability across different clusters
- Avoids test failures due to environment-specific resource configurations
- Makes resource requirements explicit and self-documenting

**Example**:

✅ **Good** - Explicit resource specifications:
```yaml
apiVersion: tekton.dev/v1
kind: TaskRun
metadata:
  name: build-task
spec:
  taskSpec:
    steps:
      - name: build
        image: <config.{{.registry.test}}>/ops/maven:latest
        computeResources:
          requests:
            cpu: "100m"
            memory: "256Mi"
          limits:
            cpu: "500m"
            memory: "512Mi"
        script: |
          mvn clean package
```

❌ **Bad** - No resource specifications:
```yaml
apiVersion: tekton.dev/v1
kind: TaskRun
metadata:
  name: build-task
spec:
  taskSpec:
    steps:
      - name: build
        image: <config.{{.registry.test}}>/ops/maven:latest
        # Missing computeResources - relies on cluster defaults
        script: |
          mvn clean package
```

**Resource Guidelines**:

| Task Type | CPU Request | Memory Request | CPU Limit | Memory Limit |
|-----------|-------------|----------------|-----------|--------------|
| Minimal (echo, scripts) | 50m | 64Mi | 100m | 128Mi |
| Standard (build/test) | 100m | 256Mi | 500m | 512Mi |
| High (intensive ops) | 500m | 512Mi | 2000m | 2Gi |

**Best Practices**:
- Set requests to the minimum resources needed for the task to run
- Set limits higher than requests to allow for bursts, but not excessively high
- Test resources should work on minimal cluster configurations (e.g., 2 CPU, 4GB memory nodes)
- Document in test description if a test requires higher resources

**When exceptions are acceptable**:
- When explicitly testing resource limit behavior or OOM scenarios
- Must be clearly documented with tags like `@high-resource-requirement`

### Principle 6: Make Kubernetes Test Data Label-Cleanable

**Guideline**: Write every E2E case so that Kubernetes residue can be discovered and removed by labels after the run. Do not rely on manual name lists, implicit namespace cleanup, or the next suite run to remove leftover resources.

**Goal**:
- All test-created namespaces must be removable by `testing.suite-name=<suite-name>`
- All test-created cluster-scoped resources must be removable by `testing.suite-name=<suite-name>`
- Namespaced helper resources created in fixed namespaces such as `tekton-pipelines` must also carry the same label so they can be cleaned explicitly
- Shared singleton objects that must not be deleted, such as `TektonConfig`, must be restored to their original state at the end of the case

**Why this matters**:
- BDD suite cleanup runs **before** the suite starts, not after it finishes
- BDD suite cleanup only targets cluster-scoped resources, and skips resources marked with `testing.cleanup=false`
- Scenario namespace cleanup only deletes the **current** namespace, only on success, and does not cover all multi-namespace patterns

This means labels are the only stable cleanup contract for E2E residue.

#### Prefer label-aware creation paths

Use BDD steps that already propagate labels from the test context whenever possible:

- `命名空间 "<...>" 已存在`
- `(创建|已导入|更新) "<resource-name>" 资源`
- `PVC "<pvc-name>" 已包含 "<description>"`

These steps are the preferred way to create Kubernetes test data because they keep the resource attached to the current test context.

✅ **Good** - Creating test data through label-aware steps:
```gherkin
背景:
    假定 我是一名管理员用户
    并且 Tekton Pipeline 组件已就绪
    并且 命名空间 "testing-example-<template.{{randNumeric 6}}>" 已存在
    并且 PVC "source" 已包含 "测试代码"

场景: 导入测试资源
    当 已导入 "pipeline run" 资源
        """
        yaml: ./testdata/pipeline/example-run.yaml
        """
```

❌ **Bad** - Creating resources through ad-hoc scripts without a label contract:
```gherkin
当 执行 "创建测试资源" 脚本成功
    | command |
    | kubectl apply -f ./testdata/pipeline/example-run.yaml |
```

Avoid this pattern for Kubernetes test data preparation whenever possible. If a custom script is unavoidable, the script must add `testing.suite-name=<suite-name>` explicitly to every created object.

#### Default to dedicated testing namespaces

Put namespaced test data in dedicated testing namespaces unless the test objective requires a fixed namespace.

**Rules**:
- Use a generated testing namespace such as `testing-<feature>-<random>`
- Create extra namespaces with `命名空间 "<...>" 已存在` when a scenario needs more than one namespace
- Do not place helper resources in `default` unless the product behavior being tested explicitly requires `default`
- Do not switch to `kube-public` or another system namespace through `命名空间 "<...>" 已存在` unless the scenario really needs to operate there

✅ **Good** - Moving helper resources out of `default`:
```gherkin
背景:
    假定 命名空间 "testing-hubs-wrapper-<template.{{randNumeric 6}}>" 已存在
    并且 已导入 "测试访问权限" 资源: "./testdata/hubs-wrapper/rbac.yaml"
```

This pattern allows the helper `ServiceAccount`, `RoleBinding`, `Secret`, and similar resources to be cleaned together with the testing namespace.

#### Treat fixed namespaces and cluster-scoped resources as explicit cleanup targets

Some tests must create resources in `tekton-pipelines` or create cluster-scoped objects. In that case:

- Ensure every helper resource still carries `testing.suite-name=<suite-name>`
- Avoid relying on object names as the primary cleanup key
- Keep disposable helper resources separate from shared singleton configuration

Examples of resources that should remain label-cleanable:
- `Namespace`
- `ClusterRole`
- `ClusterRoleBinding`
- cluster-scoped custom resources created only for the test
- namespaced helper `Secret`, `Service`, `ServiceAccount`, `PVC`, `Role`, and `RoleBinding` created under `tekton-pipelines`

#### Use restore for singleton configuration, not deletion

If the case modifies a shared singleton resource, do not design cleanup around deleting that object.

**Use restore-oriented patterns for**:
- `TektonConfig`
- operator-managed shared ConfigMaps
- other cluster-global configuration that should exist before and after the test

**Rules**:
- Prefer `update and restore after the current case` for singleton configuration
- Do not mark a singleton resource as disposable just because it was changed by the test
- If helper resources are created to support that configuration, keep those helper resources label-cleanable

**Recommended step for `TektonConfig` changes**:
- Use `更新 TektonConfig 配置并在当前 case 执行完后复原`
- Do not leave `TektonConfig` rollback to manual cleanup or a later suite run

✅ **Good** - Restoring `TektonConfig` automatically:
```gherkin
当 更新 TektonConfig 配置并在当前 case 执行完后复原
    """
    spec:
      result:
        logs_api: true
    """
```

#### Use `testing.cleanup=false` sparingly

`testing.cleanup=false` only prevents BDD pre-suite cleanup from deleting a labeled resource. It does **not** replace proper residue management.

Only use `testing.cleanup=false` when:
- The resource is a shared singleton that must survive during the suite
- Deleting it would be incorrect or disruptive

Do **not** use it as a shortcut for:
- Helper resources that can be recreated safely
- Resources that should be removed by post-run label cleanup
- Resources that were left behind only because the case has no restore step

#### Restore modified resources by default

If a case updates an existing Kubernetes resource and the resource is not a shared singleton managed through the dedicated `TektonConfig` restore step, prefer restoring it automatically in the import step.

**Recommended pattern**:
- Use `(创建|已导入|更新) "<resource-name>" 资源`
- Add `restore: true` when the step updates or replaces an existing resource that should be restored after the case

✅ **Good** - Updating a resource with automatic restore:
```gherkin
当 已导入 "Chains signing secret" 资源
    """
    yaml: ./testdata/chains/signing-secrets.yaml
    restore: true
    """
```

This pattern is preferred over leaving the changed content in the cluster and expecting later cleanup to repair it.

#### Pre-merge checklist for Kubernetes residue

Before merging a new E2E case, verify the following:

- Every namespace created by the case can be selected by `testing.suite-name=<suite-name>`
- Every cluster-scoped resource created by the case can be selected by `testing.suite-name=<suite-name>`
- Every helper resource created in `tekton-pipelines` or another fixed namespace also carries `testing.suite-name=<suite-name>`
- No helper resource is placed in `default` unless there is a test-specific reason
- Any shared singleton configuration modified by the case is restored before the case ends
- Any non-singleton resource modified by the case uses `restore: true` or another explicit restore path
- No cleanup logic depends only on scenario success, current namespace position, or manual name-by-name deletion

If a resource cannot satisfy one of these rules, document the reason in the feature or related design note and add an explicit restore or cleanup path before merging the case.

### Principle 7: Make External Tool Data Group-Scoped and Cleanable

**Guideline**: Any test data written to external tools (GitLab, Nexus, Harbor, SonarQube, external PostgreSQL, and similar systems) must be scoped to a dedicated test group or run-specific prefix, and must have a deterministic cleanup path.

**Goal**:
- Keep test writes isolated from shared team data
- Make residue cleanup targetable by group or prefix, instead of manual object lists
- Ensure failed scenarios do not leave unbounded external residue

**Why this matters**:
- Kubernetes label cleanup does not cover external systems
- `make clean-data` currently covers GitLab and Nexus only
- Hard-coded shared groups/repositories make cleanup risky and error-prone

#### Always execute tool writes inside `testGroup`

Use the generated or configured `testGroup` values as the write boundary for external systems.

**Rules**:
- Always reference external namespaces from `config.yaml`, such as:
  - `<config.{{.toolchains.gitlab.testGroup.default}}>`
  - `<config.{{.toolchains.nexus.testGroup.maven_releases}}>`
  - `<config.{{.toolchains.harbor.testGroup.default}}>`
- Do not hard-code shared namespaces like `devops`, fixed team groups, or long-lived repositories
- Keep object names run-isolated with `<namespace>` or `<template.{{randNumeric ...}}>`
- Run `make prepare-all-data` before E2E execution so runtime `testGroup` values are populated

✅ **Good** - Using runtime `testGroup` and isolated names:
```gherkin
当 执行 "准备 GitLab 项目" 脚本成功
    | command |
    | bash -x ./scripts/gitlab-prepare-project.sh --action ensure --url <config.{{.toolchains.gitlab.endpoint}}> --token <config.{{.toolchains.gitlab.token}}> --group <config.{{.toolchains.gitlab.testGroup.default}}> --project-name testing-gitops-cli-<namespace> --reset-existing |
```

❌ **Bad** - Writing into a shared hard-coded group:
```gherkin
当 执行 "准备 GitLab 项目" 脚本成功
    | command |
    | bash -x ./scripts/gitlab-prepare-project.sh --action ensure --url <config.{{.toolchains.gitlab.endpoint}}> --token <config.{{.toolchains.gitlab.token}}> --group devops --project-name e2e-demo |
```

#### Keep creation and cleanup symmetric

Every external write path must declare one cleanup contract:

- **Config-driven lifecycle**: resource is created via `prepare-all-data` and deleted by `make clean-data` (for example GitLab/Nexus)
- **Scenario-driven lifecycle**: resource is created inside a scenario and deleted in the same scenario (or in a paired teardown step)
- **Dedicated cleanup target**: resource is cleaned by a tool-specific target/script (for example SonarQube, Harbor build artifacts, Results PostgreSQL databases)

Do not merge new external writes that have no explicit cleanup owner.

#### Make script cleanup failure-safe

For script-managed external resources:
- Prefer idempotent `ensure`/`delete` actions
- Add cleanup hooks (for example `trap cleanup EXIT`) when scripts create temporary resources
- Treat cleanup as best-effort only when deletion failure is acceptable and documented

#### Pre-merge checklist for external residue

Before merging a new E2E case that writes to external tools, verify:

- All write targets use `testGroup` or a documented run-specific prefix
- No shared production/team namespace is modified without restore or explicit approval
- Cleanup path is documented and executable (`clean-data`, teardown step, or dedicated script)
- Cleanup can run repeatedly without causing destructive side effects on non-test data
- Failure paths still keep residue bounded to the same group/prefix scope

### Adding New Principles

As the test suite evolves, new principles may be added here. When proposing a new principle:

1. **Identify the Problem**: Describe what issue the principle addresses
2. **Define the Guideline**: Provide clear, actionable guidance
3. **Explain the Rationale**: Why is this principle important?
4. **Provide Examples**: Show good and bad practices
5. **Document Exceptions**: When is it acceptable to break this rule?

## Test Data Management

### Test Data Location

All test data should be organized under `testing/features/testdata/`:

```
testdata/
├── pipeline/
│   ├── pipeline-base.yaml
│   ├── pr-success.yaml
│   ├── java/
│   ├── maven/
│   └── python/
├── triggers/
│   ├── eventlistener.yaml
│   └── triggerbinding/
├── chains/
└── enhancement/
```

### YAML Resource Files

Test resources use standard Kubernetes YAML format with template support:

```yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: pipeline
spec:
  params:
    - name: tips
      default: "Hello World!"
  tasks:
    - name: echo
      taskSpec:
        steps:
          - name: echo
            image: <config.{{.registry.test}}>/ops/ubuntu:latest
            script: |
              echo "$(params.tips)"
```

### Template Variables

The BDD framework supports template variables for dynamic values:
- `<config.{{.path.to.value}}>` - Reference configuration values
- `<template.{{randNumeric 6}}>` - Generate random values
- `<namespace>` - Current test namespace
- `<bdd.feature-path>` - Feature file path

For complete template syntax, see [AlaudaDevops/bdd Documentation](https://github.com/AlaudaDevops/bdd).

### Resource Import Methods

The framework supports importing resources from YAML files with various options (single file, multiple files, with patches, etc.).

**Example**:
```gherkin
当 创建 "Pipeline" 资源
    """
    yaml: ./testdata/pipeline/pipeline-base.yaml
    """
```

For all import methods and options, see [AlaudaDevops/bdd Documentation](https://github.com/AlaudaDevops/bdd).

## Step Definitions

The BDD framework provides built-in steps for common operations. **Always prefer built-in steps** over custom scripts (see [Principle 1](#principle-1-prefer-built-in-steps-over-custom-scripts)).

**Common step categories**:
- Resource Management (create, update, delete)
- Resource Assertions (status checks, field validation)
- PipelineRun/TaskRun Status (success, failure, completion)

**For complete step reference**:
- See [AlaudaDevops/bdd Documentation](https://github.com/AlaudaDevops/bdd)
- Review existing feature files in `testing/features/`

Custom steps should only be created when built-in functionality is insufficient. See the [BDD framework documentation](https://github.com/AlaudaDevops/bdd) for implementation details.

## Configuration Management

### Main Configuration File

The `config.yaml` file contains all external service configurations:

```yaml
registry:
  test: registry.example.io:5000

toolchains:
  gitlab:
    endpoint: https://gitlab.example.io
    host: gitlab.example.io
    port: 443
    scheme: https
    username: admin
    password: <PASSWORD>
    token: <TOKEN>
    testGroup:
      default: e2e-test-group

  harbor:
    endpoint: https://harbor.example.io
    # ... similar structure
```

### Environment Variables

- `TESTING_CONFIG` - Path to configuration file (default: `./config.yaml`)
- `KUBECONFIG` - Kubernetes configuration file

### Accessing Configuration in Tests

Use template syntax in YAML files:

```yaml
image: <config.{{.registry.test}}>/ops/ubuntu:latest
```

Use in Gherkin steps:

```gherkin
| bash -x <bdd.feature-path>/../scripts/gitlab-project-webhook.sh -u <config.{{.toolchains.gitlab.endpoint}}> -t <config.{{.toolchains.gitlab.token}}> |
```

## Best Practices

### General Guidelines

1. **Write in Chinese**: All feature files use Chinese for better readability by the team
2. **One Feature Per File**: Each feature file should focus on a single functional area
3. **Use Meaningful Names**: Scenario names should clearly describe what is being tested
4. **Tag Appropriately**: Always add relevant tags for filtering and organization
5. **Reuse Background**: Put common setup steps in Background section

### Resource Management

1. **Namespace Isolation**: Each scenario should use a unique namespace
   ```gherkin
   命名空间 "testing-pipeline-<template.{{randNumeric 6}}>" 已存在
   ```

2. **Resource Cleanup**: Resources are automatically cleaned up unless `@skip-cleanup-namespace` tag is used

3. **Resource Limits**: Always specify resource limits in test resources
   ```yaml
   computeResources:
     requests:
       cpu: "50m"
       memory: "64Mi"
     limits:
       cpu: "100m"
       memory: "128Mi"
   ```

### Test Isolation

1. **Independent Tests**: Each scenario should be runnable independently
2. **No Shared State**: Avoid dependencies between scenarios
3. **Unique Names**: Use random suffixes for resource names to avoid conflicts
4. **Dedicated Namespaces**: Each test should create its own namespace

### Timeouts and Intervals

Always specify appropriate timeouts and check intervals:

```gherkin
并且 "Pipeline" 资源检查通过
    | apiVersion    | name     | path            | value        | interval | timeout |
    | tekton.dev/v1 | pipeline | $.metadata.name | pipeline     | 5s       | 30s     |
```

- **interval**: How often to check (e.g., `5s`, `10s`)
- **timeout**: Maximum wait time (e.g., `30s`, `1m`, `10m`)

### Error Handling

1. **Expected Failures**: Some tests verify failure scenarios
   ```gherkin
   并且 PipelineRun "pr-failed" 执行失败
   ```

2. **Detailed Assertions**: Use JSONPath for specific field validation
   ```gherkin
   | path                                                    | value  |
   | $.status.conditions[?(@.type == 'Succeeded')][0].reason | Failed |
   ```

### Helper Scripts

1. **Location**: Place helper scripts in `testing/scripts/`
2. **Naming**: Use descriptive names: `gitlab-project-webhook.sh`, `setup-chains.sh`
3. **Error Handling**: Scripts should exit with non-zero on failure
4. **Documentation**: Add comments explaining script purpose and parameters

## Running Tests

### Using Makefile

The Makefile provides several targets:

```bash
# Run all tests (parallel + serial)
make test

# Run only parallel tests
make test-parallel

# Run only serial tests
make test-serial

# Run with custom tags
make test TAGS="@smoke"

# Run upgrade tests
make test-upgrade-prepare
make test-upgrade-upgrade

# Generate and view report
make report
```

### Manual Execution

```bash
# Run with godog
go test -timeout=1h -v -count 1 . \
  --godog.concurrency=3 \
  --godog.format=allure \
  --godog.tags="@e2e && ~@manual"

# Run specific feature
go test -v . --godog.paths=features/pipeline.base.feature
```

### Test Tags for Filtering

```bash
# Run only smoke tests
--godog.tags="@smoke"

# Exclude manual tests
--godog.tags="~@manual"

# Combine tags (AND)
--godog.tags="@smoke && @api"

# Combine tags (OR)
--godog.tags="@smoke,@api"
```

## Debugging Tests

### Enable Verbose Output

```bash
go test -v . --test.v
```

### Run Single Scenario

Use the scenario tag:

```bash
go test -v . --godog.tags="@tektoncd-pipeline-basic-001"
```

### Access Kubernetes Resources

During test execution, you can inspect resources:

```bash
# List resources in test namespace
kubectl get all -n testing-pipeline-<namespace>

# View PipelineRun logs
kubectl logs -n <namespace> <pod-name>

# Describe resource
kubectl describe pipelinerun -n <namespace> <pr-name>
```

### Allure Reports

Test results are saved to `allure-results/`. Generate HTML report:

```bash
allure generate --clean
allure open
```

## Common Patterns

### Checking Resource Existence

```gherkin
那么 "Pipeline" 资源检查通过
    | apiVersion    | name     | path            | value    | interval | timeout |
    | tekton.dev/v1 | pipeline | $.metadata.name | pipeline | 5s       | 30s     |
```

### Checking Resource Non-Existence

```gherkin
那么 资源 "Pipeline" 不存在
    | apiVersion    | name     | interval | timeout |
    | tekton.dev/v1 | pipeline | 5s       | 1m      |
```

### Waiting for Pod Status

```gherkin
那么 Pod 资源检查通过
    | name           | path           | value     | interval | timeout |
    | git-run.*      | $.status.phase | Succeeded | 10s      | 3m      |
```

### Using Regular Expressions

JSONPath names support regex:

```gherkin
| name      | path            | value    |
| ^pr-.*$   | $.status.phase  | Succeeded |
```

### Executing Helper Scripts

```gherkin
并且 执行 "初始化代码仓库" 脚本成功
    | command |
    | bash -x <bdd.feature-path>/../scripts/push-git-repo.sh --local <bdd.feature-path>/testdata/coderepos/git-clone.tgz |
```

## Troubleshooting

### Common Issues

1. **Timeout Errors**
   - Increase timeout values in assertions
   - Check if resources are actually being created
   - Verify Kubernetes cluster has sufficient resources

2. **Namespace Already Exists**
   - Use random namespace suffixes: `<template.{{randNumeric 6}}>`
   - Check for cleanup failures in previous runs

3. **Image Pull Errors**
   - Verify registry configuration in `config.yaml`
   - Check image pull secrets are properly configured
   - Ensure registry is accessible from cluster

4. **Configuration Template Errors**
   - Verify config.yaml has required fields
   - Check template syntax: `<config.{{.path.to.value}}>`
   - Ensure TESTING_CONFIG environment variable is set

5. **Step Definition Not Found**
   - Verify step is registered in `main_test.go`
   - Check step pattern matches exactly (including regex)
   - Ensure built-in steps are imported

### Debug Mode

Set environment variables for detailed logging:

```bash
DEBUG=true TEST_VERBOSE=true make test
```

### Preserve Resources for Investigation

Use the cleanup flag:

```bash
go test -v . --bdd.cleanup=false
```

Or add tag to scenario:

```gherkin
@skip-cleanup-namespace
场景: Debug scenario
```

## Examples

### Complete Feature File Example

```gherkin
# language: zh-CN

@cicd
@tektoncd-operator
@tektoncd-pipeline
@e2e
功能: 流水线基本流程

    作为一名开发者
    我希望能够使用 Tekton Pipeline 来编排和运行我的流水线
    以便于我可以自动化构建、测试和部署我的应用程序

    背景:
        假定 我是一名管理员用户
        并且 Tekton Operator 组件已就绪
        并且 Tekton Pipeline 组件已就绪
        并且 命名空间 "testing-pipeline-<template.{{randNumeric 6}}>" 已存在

    @smoke
    @api
    @tektoncd-pipeline-basic-001
    场景: 创建&更新&删除 Pipeline 流水线-YAML
        假如 我是一个已登录的用户
        当 创建 "Pipeline" 资源
            """
            yaml: ./testdata/pipeline/pipeline-base.yaml
            """
        那么 资源导入结果检查通过
            | path    | value |
            | $.error | false |
        并且 "Pipeline" 资源检查通过
            | apiVersion    | name     | path                     | value        | interval | timeout |
            | tekton.dev/v1 | pipeline | $.spec.params[0].default | Hello World! | 5s       | 30s     |

        当 删除 "Pipeline" 资源
            | apiVersion    | name     |
            | tekton.dev/v1 | pipeline |
        那么 资源 "Pipeline" 不存在
            | apiVersion    | name     | interval | timeout |
            | tekton.dev/v1 | pipeline | 5s       | 1m      |
```

### Test Data Example

```yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: pipeline
spec:
  params:
    - name: tips
      default: "Hello World!"
  tasks:
    - name: echo
      taskSpec:
        steps:
          - name: echo
            image: <config.{{.registry.test}}>/ops/ubuntu:latest
            computeResources:
              requests:
                cpu: "50m"
                memory: "64Mi"
              limits:
                cpu: "100m"
                memory: "128Mi"
            script: |
              echo "$(params.tips)"
```

## References

- [Running E2E Tests](./run_e2e.mdx) - Guide for running the E2E test suite
- [Godog Documentation](https://github.com/cucumber/godog) - BDD framework for Go
- [Gherkin Syntax](https://cucumber.io/docs/gherkin/reference/) - Language reference
- [AlaudaDevops BDD](https://github.com/AlaudaDevops/bdd) - BDD framework used in this project
- [Allure Reports](https://docs.qameta.io/allure/) - Test reporting framework
