---
title: TriggerTemplate as TaskRun or PipelineRun Runtime Configuration Template
authors:
  - qingliu@alauda.io
creation-date: 2025-06-30
last-updated: 2025-07-02
status: proposed
---

# TEP-0001: TriggerTemplate as TaskRun or PipelineRun Runtime Configuration Template

## Summary

This proposal aims to leverage existing `TriggerTemplate` resources as runtime configuration templates for `Task` or `Pipeline` execution, eliminating the need to repeatedly configure similar runtime settings for each `TaskRun` or `PipelineRun`.

By using `TriggerTemplate` as a configuration template, users can define standardized runtime configurations for individual tasks or pipelines, improving efficiency and consistency.

Currently, each configuration template is associated with a single task or pipeline, but a task or pipeline can have multiple related configuration templates.

## Motivation

Currently, when creating `TaskRun` or `PipelineRun`, users often need to repeatedly configure similar execution settings such as `params`, `workspaces`, `serviceAccountName`, `podTemplate` etc.
This repetitive configuration work is inefficient and prone to errors. Additionally, maintaining consistency across multiple executions of the same task or pipeline becomes challenging.

### Goals

- Eliminate repetitive runtime configuration for `TaskRun` or `PipelineRun` executions
  - This mechanism is also applicable to other `CustomRun` resources
- Provide standardized runtime configuration templates using existing `TriggerTemplate` resources
- Enable task or pipeline-specific configuration templates with support for multiple configurations per task or pipeline
- Support default configuration designation through labeling mechanisms, and users can override the default configuration by specifying a different configuration template
- Maintain compatibility with existing Tekton Triggers APIs

### Non-Goals

- Modifying the core `TriggerTemplate` API structure
- Creating new resource types for runtime configuration
- Automating the selection of configuration templates
- Supporting dynamic template selection based on runtime conditions

### Use Cases

1. **Standardized Task and Pipeline Execution**
   - Teams can use predefined runtime configurations for common task and pipeline execution scenarios
   - Reduces configuration errors and ensures consistency across multiple executions of the same task or pipeline

2. **Environment-Specific Configurations**
   - Different runtime configurations for development, staging, and production environments
   - Environment-specific parameters, workspaces, and security settings

3. **Task and Pipeline Variants**
   - Multiple configuration templates for the same task or pipeline (e.g., different `params`, `workspaces`, `serviceAccountName`, `podTemplate`)
   - Support for different execution modes or requirements

4. **Template Reusability**
   - (Optional) Share common runtime configurations across multiple tasks and pipelines
   - Reduce duplication of configuration code

### Requirements

- Must utilize existing `TriggerTemplate` resources without API modifications
- Must support both task-specific and pipeline-specific configuration templates
- Must allow multiple `TriggerTemplates` per task or pipeline with default designation mechanism
- Must support all `TaskRun` and `PipelineRun` runtime configuration options (params, workspaces, serviceAccountName, podTemplate, taskRunSpecs, etc.)
- Must maintain backward compatibility with existing trigger-based usage
- Must support template merge rules for combining multiple configuration templates

## Proposal

Use `TriggerTemplate` resources as runtime configuration templates for `TaskRun` or `PipelineRun` execution.
Each `TriggerTemplate` will be associated with a specific task or pipeline and can contain predefined runtime configurations including `params`, `workspaces`, `serviceAccountName`, `podTemplate` etc. Other runtime configuration parameters can also be used as `TriggerTemplate` configuration items.

### Notes and Caveats

- This approach reuses existing `TriggerTemplate` resources, avoiding the need for new resource types
- `TriggerTemplates` used as runtime configuration templates should not be used in actual trigger scenarios to avoid conflicts
- The selection of configuration templates will be handled by the UI, not automatically by the CLI or system
- Users can still create `TaskRun` or `PipelineRun` resources directly without using templates when needed

## Design Details

### TriggerTemplate Structure

> We completely reuse the existing `TriggerTemplate` resource without any modifications.

A `TriggerTemplate` is a resource that specifies a blueprint for the resource. Currently, `TriggerTemplate` supports the following Tekton Pipelines resources:

| v1alpha1 | v1beta1 |
| ----------- | ---- |
| Pipeline | Pipeline |
| PipelineRun | PipelineRun |
| Task | Task |
| TaskRun | TaskRun |
| ClusterTask | ClusterTask |
| Condition | |
| PipelineResource | |

As [`TriggerTemplate` API Reference](../apis/kubernetes_apis/triggers/triggertemplate.mdx) shows the complete definition of this resource, it is very flexible.

We do not utilize all capabilities of `TriggerTemplate` when using it as a runtime configuration template. We have established some conventions for this usage.

- We only use the latest `triggers.tekton.dev/v1beta1` API version.
- We use the `metadata` to store the template information. Such as `name`, `labels`, `annotations` etc.
- We do not use the `spec.params` field.
- We use the `spec.resourcetemplates` field to store the runtime configuration.
- We only support configuring a single resource in `resourcetemplates`.

:::note
**Important**:

- Since we store code snippets in `resourcetemplates`, we do not guarantee that the resources created from these templates will execute correctly.
- We do not limit the other usages of `TriggerTemplate`, these conventions are only applicable when using `TriggerTemplate` as a runtime configuration template.
:::

A typical `TriggerTemplate` used as a runtime configuration template will look like this:

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
  name: pipeline-runtime-config
  labels:
    # tekton.dev/task: <task-name>
    tekton.dev/pipeline: <pipeline-name>
    triggertemplate.triggers.tekton.dev/usage: <runtime-config>
    triggertemplate.triggers.tekton.dev/runtime-config-default: "true" # Optional: marks as default
  annotations:
    tekton.dev/displayName: "Pipeline Runtime Configuration"
    tekton.dev/description: "Runtime configuration for development environment"
spec:
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: <pipeline-name>-
      spec:
        pipelineRef:
          name: <pipeline-name>
        # Predefined runtime configurations
        params:
          - name: image-tag
            value: <image-tag>
          - name: environment
            value: <environment>
        workspaces:
          - name: source
            emptyDir: {}
          - name: cache
            persistentVolumeClaim:
              claimName: pipeline-cache
        serviceAccountName: pipeline-sa
        podTemplate:
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
          nodeSelector:
            kubernetes.io/os: linux
```

On the following sections, we will detail the configuration conventions for `TriggerTemplate` used as runtime configuration templates.

### Configuration Conventions

To use existing `TriggerTemplate` resources as runtime configuration templates, you need to follow specific conventions for labels and annotations.
This section details the required conventions and their meanings.

#### Label Conventions

- `triggertemplate.triggers.tekton.dev/usage: runtime-config`
  - **Purpose**: Identifies this TriggerTemplate's purpose
  - **Value**: Must be set to `runtime-config` to distinguish from trigger-based templates. In the future, there may be other types of values.
  - **Example**: `triggertemplate.triggers.tekton.dev/usage: runtime-config`

- (Optional) `tekton.dev/task: <task-name>`
  - **Purpose**: Associates the template with a specific task
  - **Value**: The name of the task this template applies to
  - **Example**: `tekton.dev/task: build-task`

- (Optional) `tekton.dev/pipeline: <pipeline-name>`
  - **Purpose**: Associates the template with a specific pipeline
  - **Value**: The name of the pipeline this template applies to
  - **Example**: `tekton.dev/pipeline: build-pipeline`

- (Optional) `triggertemplate.triggers.tekton.dev/runtime-config-default: "true"`
  - **Purpose**: Marks this template as the default configuration for the task or pipeline
  - **Value**: Set to `"true"` to designate as default, omit otherwise
  - **Usage**: When multiple templates exist for the same task or pipeline, this one will be used as the default
  - **Example**: `triggertemplate.triggers.tekton.dev/runtime-config-default: "true"`

> **Important**: `tekton.dev/task` and `tekton.dev/pipeline` labels must have exactly one value.

#### Annotation Conventions

The following annotations provide additional metadata for runtime templates:

- (Optional) `tekton.dev/displayName: <display-name>`
  - **Purpose**: Human-readable display name of the template
  - **Value**: Display name of the template
  - **Example**: `tekton.dev/displayName: "Production environment configuration"`

- (Optional) `tekton.dev/description: <description>`
  - **Purpose**: Human-readable description of the template's purpose
  - **Value**: Brief description explaining when and how to use this template
  - **Example**: `tekton.dev/description: "Production environment configuration with high security settings"`

#### ResourceTemplate Conventions

- We only support configuring a single resource in `resourcetemplates`.
- If all required parameters have values, theoretically, based on this `TriggerTemplate`, a valid `PipelineRun` or `TaskRun` resource can be created and executed successfully.
  - Basic `apiVersion`, `kind`, `metadata` are still required.
  - The corresponding `pipelineRef` (for `PipelineRun`) or `taskRef` (for `TaskRun`) must be specified.
- All other fields supported by PipelineRun and TaskRun specifications can be configured as needed.

  - `PipelineRun`

    ```yaml
    apiVersion: triggers.tekton.dev/v1beta1
    kind: TriggerTemplate
    metadata:
    spec:
      resourcetemplates:
        - apiVersion: tekton.dev/v1
          kind: PipelineRun
          metadata:
            generateName: build-pipeline-
          spec:
            pipelineRef:
              name: build-pipeline
            # Additional PipelineRun fields can be configured here
            # such as params, workspaces, serviceAccountName, podTemplate, taskRunSpecs, etc.
    ```

    > More details about `PipelineRun` configuration can be found in [`PipelineRun` API Reference](../apis/kubernetes_apis/pipelines/tekton.dev_pipelineruns.mdx)

  - `TaskRun`

    ```yaml
    apiVersion: triggers.tekton.dev/v1beta1
    kind: TriggerTemplate
    metadata:
    spec:
      resourcetemplates:
        - apiVersion: tekton.dev/v1
          kind: TaskRun
          metadata:
            generateName: build-task-
          spec:
            taskRef:
              name: build-task
            # Additional TaskRun fields can be configured here
            # such as params, workspaces, serviceAccountName, podTemplate, etc.
    ```

    > More details about `TaskRun` configuration can be found in [`TaskRun` API Reference](../apis/kubernetes_apis/pipelines/tekton.dev_taskruns.mdx)

### Template Selection Rules

When multiple templates exist for the same task or pipeline, the following selection logic applies:

1. **Template Availability Check**:
   - Frontend queries `TriggerTemplates` with label `triggertemplate.triggers.tekton.dev/usage: runtime-config`
   - Filters by task label `tekton.dev/task=<task-name>` or pipeline label `tekton.dev/pipeline=<pipeline-name>`
   - If matching templates exist, they are available for selection
   - If no matching templates exist, no templates are available for the task or pipeline

2. **Default Template Selection**:
   - Among available templates, identify those with `triggertemplate.triggers.tekton.dev/runtime-config-default: "true"`
   - If multiple default templates exist, select the one with the latest creation timestamp
   - If only one default template exists, select that template
   - If no default template exists, no template is automatically selected

### Template Merge Rules

Since a task or pipeline can select multiple runtime configuration templates, we need to define template merge rules.
We reference the merge logic of [`Pod Templates`](https://tekton.dev/docs/pipelines/podtemplates/#pod-templates) to define the merge rules for runtime configuration templates.

- `params`, `workspaces`, `podTemplate.env`, `podTemplate.volumes` fields are merged by the name value in the array elements.
- Other fields use standard merge logic where later values override earlier ones. If the field is an object, it will be recursively merged.

#### Template Merge Example

The following example demonstrates how multiple templates are merged when selected together:

:::details{title="Base Configuration Template"}

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
  name: base-config
  labels:
    triggertemplate.triggers.tekton.dev/usage: runtime-config
    tekton.dev/pipeline: build-pipeline
spec:
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: build-pipeline-
      spec:
        pipelineRef:
          name: build-pipeline
        # params merged by name field
        params:
          - name: environment
            value: "development"
          - name: image-tag
            value: "latest"
          - name: registry
            value: "docker.io"
        # workspaces merged by name field
        workspaces:
          - name: source
            emptyDir: {}
          - name: cache
            persistentVolumeClaim:
              claimName: default-cache
          - name: config
            configMap:
              name: app-config
        # podTemplate merged by name field
        podTemplate:
          nodeSelector:
            environment: dev
            kubernetes.io/os: linux
          env:
            - name: BUILD_ENV
              value: "development"
            - name: LOG_LEVEL
              value: "info"
          volumes:
            - name: shared-config
              configMap:
                name: shared-config
            - name: temp-storage
              emptyDir: {}
          securityContext:
            runAsUser: 1000
```

:::

:::details{title="Additional Configuration Template"}

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
  name: additional-config
  labels:
    triggertemplate.triggers.tekton.dev/usage: runtime-config
    tekton.dev/pipeline: build-pipeline
spec:
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: build-pipeline-
      spec:
        pipelineRef:
          name: build-pipeline
        # params merged by name - override same names, add new ones
        params:
          - name: environment
            value: "production"  # Override "development" from base config
          - name: build-type
            value: "optimized"   # Add new parameter
        # workspaces merged by name - override same names, add new ones
        workspaces:
          - name: source
            persistentVolumeClaim:
              claimName: prod-source  # Override emptyDir from base config
          - name: secrets
            secret:
              secretName: prod-secrets  # Add new workspace
        # podTemplate merged by name - override same names, add new ones
        podTemplate:
          nodeSelector:
            environment: production  # Override base config
            kubernetes.io/arch: amd64
          env:
            - name: BUILD_ENV
              value: "production"  # Override "development" from base config
            - name: SECURITY_MODE
              value: "strict"      # Add new environment variable
          volumes:
            - name: shared-config
              secret:
                secretName: prod-shared-config  # Override configMap from base config
            - name: security-certs
              secret:
                secretName: security-certs  # Add new volume
          securityContext:
            runAsNonRoot: true  # Override base config
            runAsUser: 1001     # Override 1000 from base config
```

:::

:::details{title="Merged Configuration Result"}

```yaml
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  generateName: build-pipeline-
spec:
  pipelineRef:
    name: build-pipeline
  # params merge result - merged by name
  params:
    - name: environment
      value: "production"  # From additional config, overrides "development" from base
    - name: image-tag
      value: "latest"      # From base config, unchanged
    - name: registry
      value: "docker.io"   # From base config, unchanged
    - name: build-type
      value: "optimized"   # From additional config, newly added
  # workspaces merge result - merged by name
  workspaces:
    - name: source
      persistentVolumeClaim:
        claimName: prod-source  # From additional config, overrides emptyDir from base
    - name: cache
      persistentVolumeClaim:
        claimName: default-cache  # From base config, unchanged
    - name: config
      configMap:
        name: app-config  # From base config, unchanged
    - name: secrets
      secret:
        secretName: prod-secrets  # From additional config, newly added
  # podTemplate merge result - merged by name
  podTemplate:
    nodeSelector:
      environment: production  # From additional config, overrides "dev" from base
      kubernetes.io/os: linux
      kubernetes.io/arch: amd64
    env:
      - name: BUILD_ENV
        value: "production"  # From additional config, overrides "development" from base
      - name: LOG_LEVEL
        value: "info"        # From base config, unchanged
      - name: SECURITY_MODE
        value: "strict"      # From additional config, newly added
    volumes:
      - name: shared-config
        secret:
          secretName: prod-shared-config  # From additional config, overrides configMap from base
      - name: temp-storage
        emptyDir: {}         # From base config, unchanged
      - name: security-certs
        secret:
          secretName: security-certs  # From additional config, newly added
    securityContext:
      runAsNonRoot: true  # From additional config, overrides base config
      runAsUser: 1001     # From additional config, overrides 1000 from base
```

:::

##### Merge Rules Summary

###### 1. params Merge Rules

- **Merged by `name` field**: If two templates have parameters with the same name, the later template overrides the earlier one
- **Preserve different names**: Parameters with different names are preserved
- **Example**: `environment` parameter is overridden from `"development"` to `"production"`, while `image-tag` and `registry` remain unchanged

###### 2. workspaces Merge Rules

- **Merged by `name` field**: If two templates have workspaces with the same name, the later template overrides the earlier one
- **Preserve different names**: Workspaces with different names are preserved
- **Example**: `source` workspace is overridden from `emptyDir` to `persistentVolumeClaim`, while `cache` and `config` remain unchanged

###### 3. podTemplate Merge Rules

- **env merged by `name` field**: Environment variables are merged by name, same names are overridden
- **volumes merged by `name` field**: Volumes are merged by name, same names are overridden
- **Other fields use standard merge**: `nodeSelector`, `securityContext` and other fields use standard merge logic. If the field is an object, it will be recursively merged.
- **Example**:
  - `BUILD_ENV` is overridden from `"development"` to `"production"`
  - `shared-config` volume is overridden from `configMap` to `secret`
  - `securityContext` fields are recursively merged (same fields overridden, different fields preserved)

This merge mechanism ensures configuration flexibility and composability, allowing users to create complex runtime configurations by combining multiple templates.

### Configuration Validation and Cleanup

After merging multiple configuration templates, the consuming system performs a final validation step to ensure the resulting configuration is clean and valid.
This step removes any `params` or `workspaces` that are not actually defined in the target `Pipeline` or `Task` specification.

The validation process includes:

1. **Parameter Validation**: Filters out `params` that are not declared in the target `Pipeline` or `Task` specification
2. **Workspace Validation**: Removes `workspaces` that are not defined in the target `Pipeline` or `Task` specification

This validation ensures that the final runtime configuration only contains relevant and valid configuration items, preventing potential issues and maintaining clean, efficient resource definitions that follow Tekton best practices.

### Runtime Configuration Scenarios

The following sections demonstrate different application scenarios and how to configure them in `TriggerTemplate` runtime configuration templates:

#### Runtime Configuration Parameters

PipelineRuns can define parameters that can be used during execution:

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
spec:
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: <pipeline-name>-
      spec:
        pipelineRef:
          name: <pipeline-name>
        # Only the following fields are runtime configuration
        params:
          - name: image-tag
            value: <image-tag>
          - name: environment
            value: <environment>
```

TaskRuns can define parameters that can be used during execution:

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
spec:
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: TaskRun
      metadata:
        generateName: <task-name>-
      spec:
        taskRef:
          name: <task-name>
        # Only the following fields are runtime configuration
        params:
          - name: image-tag
            value: <image-tag>
          - name: environment
            value: <environment>
```

> Since the configuration items of `TaskRun` and `PipelineRun` are basically the same, only the configuration items of `PipelineRun` are shown in the following examples.

#### Workspace Configuration

Predefined workspace configurations can be included in the template:

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
spec:
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: <pipeline-name>-
      spec:
        pipelineRef:
          name: <pipeline-name>
        # Only the following fields are runtime configuration
        workspaces:
          - name: source
            emptyDir: {}
          - name: cache
            persistentVolumeClaim:
              claimName: pipeline-cache
          - name: shared
            configMap:
              name: shared-config
```

#### ServiceAccount and Security

Security configurations can be predefined in the template:

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
spec:
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: <pipeline-name>-
      spec:
        pipelineRef:
          name: <pipeline-name>
        # Only the following fields are runtime configuration
        taskRunTemplate:
          serviceAccountName: <service-account-name>
          podTemplate:
            securityContext:
              runAsNonRoot: true
              runAsUser: 1000
              fsGroup: 1000
```

#### Pod Template Configuration

Advanced pod configurations can be included:

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
spec:
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: <pipeline-name>-
      spec:
        pipelineRef:
          name: <pipeline-name>
        # Only the following fields are runtime configuration
        podTemplate:
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
          nodeSelector:
            kubernetes.io/os: linux
          tolerations:
            - key: "dedicated"
              operator: "Equal"
              value: "pipeline"
              effect: "NoSchedule"
          affinity:
            nodeAffinity:
              requiredDuringSchedulingIgnoredDuringExecution:
                nodeSelectorTerms:
                  - matchExpressions:
                      - key: kubernetes.io/os
                        operator: In
                        values:
                          - linux
```

## Design Evaluation

### Reusability

- Templates can be reused across multiple TaskRun and PipelineRun executions
- Common configurations can be shared across different tasks and pipelines through standardized conventions
- Parameterization allows for customization while maintaining consistency
- Template merge rules enable composition of multiple configuration templates

### Simplicity

- Uses existing `TriggerTemplate` resources without API changes, leveraging familiar structure
- Clear labeling conventions (`triggertemplate.triggers.tekton.dev/usage`, `tekton.dev/task`, `tekton.dev/pipeline`) for easy identification
- Standardized annotation conventions (`tekton.dev/displayName`, `tekton.dev/description`) for metadata
- Single resource template limitation simplifies configuration and reduces complexity

### Flexibility

- Supports multiple configuration templates per task or pipeline with default designation mechanism
- Allows explicit template selection or automatic default template resolution
- Comprehensive runtime configuration support including `params`, `workspaces`, `serviceAccountName`, `podTemplate`, `taskRunSpecs`, etc.
- Template merge rules provide flexible composition capabilities
- Maintains compatibility with existing trigger-based usage patterns

### Consistency

- Standardized configuration patterns across task and pipeline executions
- Reduces configuration errors through templating and validation
- Ensures consistent security settings, resource allocations, and execution environments
- Clear template selection rules prevent ambiguity in configuration resolution

### User Experience

- Eliminates repetitive runtime configuration work for TaskRun and PipelineRun
- Provides intuitive template selection mechanisms with default configuration support
- Clear labeling and annotation conventions improve discoverability and documentation
- Maintains backward compatibility with existing TriggerTemplate usage
- Human-readable display names and descriptions enhance template management

### Performance

- No additional API overhead since existing TriggerTemplate resources are reused
- Efficient template resolution through Kubernetes label-based filtering
- Minimal impact on existing trigger functionality due to clear separation of concerns
- Single resource template limitation reduces processing complexity
- Template merge rules are based on proven Kubernetes merge patterns

## Alternatives

1. **New Resource Type**: Creating dedicated TaskRunTemplate and PipelineRunTemplate resources
   - Pros: Clear separation of concerns, native API support with proper validation
   - Cons: Additional API complexity and maintenance overhead, breaks the principle of reusing existing resources

2. **ConfigMap-based Templates**: Using ConfigMaps to store template configurations
   - Pros: Simple implementation using existing Kubernetes resources
   - Cons: Limited validation and type safety, poor discoverability and management experience

3. **Pipeline/Task Annotations**: Embedding configuration directly in Pipeline or Task resources
   - Pros: Tight coupling with pipeline/task definition, single source of truth
   - Cons: Reduces flexibility and reusability, violates separation of concerns principle

4. **External Configuration Management**: Using external tools like Helm, Kustomize, or GitOps
   - Pros: Leverages existing ecosystem tools, advanced templating capabilities
   - Cons: Requires additional tooling and infrastructure, not integrated with Tekton's native resource model

## Implementation Plan

### Implementation Steps

#### Step 1: Template Discovery and Display

- **Frontend Template Discovery**
  - Query `TriggerTemplates` with label `triggertemplate.triggers.tekton.dev/usage: runtime-config` and filter by task/pipeline labels
  - Display available templates in UI with metadata (displayName, description) for user selection

#### Step 2: Template Selection Interface

- **Multi-Template Selection**
  - Allow users to select multiple templates

#### Step 3: Template Merge Implementation

- **Runtime Parameter Merging**
  - Implement template merge rules to combine `params`, `workspaces`, `podTemplate` based on defined rules
  - Apply merged configuration to PipelineRun/TaskRun creation form with parameter override support

### Testing Plan

#### UI Automation Testing

- **Template Discovery Tests**
  - Test template filtering by labels
  - Validate template display and metadata
  - Test template selection interface

- **Template Merge Tests**
  - Test multi-template selection
  - Validate merge rules implementation
  - Test parameter override functionality

- **End-to-End Workflow Tests**
  - Test complete template selection and application
  - Validate PipelineRun/TaskRun creation with templates
  - Test error handling and edge cases

### Upgrade and Migration Strategy

Not applicable.

### Implementation Pull Requests

TODO

## References

- [Tekton Triggers Documentation](https://tekton.dev/docs/triggers/)
- [Tekton Pipeline Documentation](https://tekton.dev/docs/pipelines/)
- [Pod Templates Documentation](https://tekton.dev/docs/pipelines/podtemplates/)
- [Kubernetes Labeling Best Practices](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/)
- API References
  - [TriggerTemplate API Reference](../apis/kubernetes_apis/triggers/triggertemplate.mdx)
  - [PipelineRun API Reference](../apis/kubernetes_apis/pipelines/tekton.dev_pipelineruns.mdx)
  - [TaskRun API Reference](../apis/kubernetes_apis/pipelines/tekton.dev_taskruns.mdx)
