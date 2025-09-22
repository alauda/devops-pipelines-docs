---
title: Relate TriggerTemplate to Trigger
authors:
  - lfyou@alauda.io
creation-date: 2025-09-18
last-updated: 2025-09-18
status: proposed
---

# TEP-0001: Relate TriggerTemplate to Trigger

## Record of changes

| Order | Change of content | Reason for change | Change of time | Change of executor | Approved by |
| :---- | :---------------- | :---------------- | -------------- | :----------------- | :---------- |

## Summary

This proposal aims to relate existing `TriggerTemplate` resources to `Trigger` resources.

In the process of creating a `Trigger`, you can easily refer to an existing `TriggerTemplate` to complete the creation work.

## Motivation

Currently, when creating `Trigger`, users often need to repeatedly configure similar template such as `params`, `workspaces`, `serviceAccountName`, `podTemplate` etc.
This repetitive configuration is inefficient and cumbersome, and is not conducive to unified maintenance.

### Goals

- Supports direct use of an existing `TriggerTemplate` when creating `Trigger`
- The parameters passed through the `TriggerBinding` of the `Trigger` event can be used in the `TriggerTemplate`
- Maintain compatibility with existing Tekton Triggers APIs

### Non-Goals

- Modifying the core `TriggerTemplate` API structure
- Provides a new resource type for `Trigger` creation to use
- Automating the selection of configuration templates

### Use Cases

1. **Trigger Refer to TriggerTemplate**

   - Supports direct use of an existing `TriggerTemplate` when creating `Trigger`

2. **TriggerTemplate uses the TriggerBinding parameters**

   - The parameters of the `TriggerBinding` can be used in the `TriggerTemplate`

### Requirements

- Must utilize existing `TriggerTemplate` resources without API modifications
- Must maintain backward compatibility with existing trigger-based usage
- Must support template merge rules for combining multiple configuration templates

## Design Details

### Core ideas

The core of this solution is to introduce new metadata (Labels) for `TriggerTemplate` to be able to declare their required parameter sources (i.e. `TriggerBinding`). Compatible `TriggerTemplate` can then be auto-discovered based on the selected `TriggerBinding` when the `Trigger` is created.

#### Declaration

When creating a `TriggerTemplate`, the user specifies `TriggerBinding` that are compatible with its design.The system records this relationship in the Label of the `TriggerTemplate`.

#### Discovery

When creating a `Trigger`, when the user selects a `TriggerBinding`, the system can query the Label Selector to find all the `TriggerTemplate` declared to be compatible with this `TriggerBinding` for the user to select.

### Label Design

We will use a specific Label on the `TriggerTemplate` to identify its association with the `TriggerBinding`.

| Key                                          | Value         |
| :------------------------------------------- | :------------ |
| triggertemplate.triggers.tekton.dev/bindings | <bindingName> |

**Instructions**:

- <bindingName> is the name of the resource for `TriggerBinding`

**Example**:

```yaml
labels:
  triggers.tekton.dev/bindings: "github-push-binding"
```

### Parameter Mapping and verification

`Triggertemplate` spec.params field defines the list of parameters it needs. `Triggerbinding` spec.params field defines the list of parameters it can provide.
**Compatibility rules**:
`TriggerBinding`B can be used to instantiate `TriggerTemplate`T if and only if the set of parameters that B can provide contains the set of parameters required by T (disregarding parameters with default values).

### Trigger template discovery mechanism

In a user interface or automated process, the steps to create a `Trigger` are as follows:

1. The user selects a name for `Triggerbinding` (e.g. gitlab-push).
2. The system uses Label Selector triggertemplate.triggers.tekton.dev/bindings=gitlab-push query all of `TriggerTemplate`.
3. The system displays a list of filtered `TriggerTemplate` to the user.
4. The user selects a `TriggerTemplate` reference from the list to configure the `Trigger`.

### Example of a resource definition

#### TriggerBinding

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: ClusterTriggerBinding
metadata:
  labels:
    cpaas.io/tool: gitlab
    operator.tekton.dev/operand-name: tektoncd-triggers
  name: gitlab-push
spec:
  params:
    - name: project-id
      value: $(body.project.id)
    - name: project-name
      value: $(body.project.name)
    - name: project-path
      value: $(body.project.path_with_namespace)
    - name: project-web-url
      value: $(body.project.web_url)
    - name: git-repo-url
      value: $(body.project.git_http_url)
    - name: git-repo-ssh-url
      value: $(body.project.git_ssh_url)
    - name: git-repo-name
      value: $(body.repository.name)
    - name: user-name
      value: $(body.user_name)
    - name: user-username
      value: $(body.user_username)
    - name: user-email
      value: $(body.user_email)
    - name: git-revision
      value: $(body.ref)
    - name: git-commit-sha
      value: $(body.checkout_sha)
    - name: git-commit-message
      value: $(body.commits[0].message)
    - name: git-commit-timestamp
      value: $(body.commits[0].timestamp)
```

#### TriggerTemplate

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
  name: my-template
  labels:
    triggertemplate.triggers.tekton.dev/bindings: "gitlab-push"
spec:
  params:
    - name: project-id
    - name: project-name
    - name: project-path
    - name: project-web-url
    - name: git-repo-url
    - name: git-repo-ssh-url
    - name: git-repo-name
    - name: user-name
    - name: user-username
    - name: user-email
    - name: git-revision
    - name: git-commit-sha
    - name: git-commit-message
    - name: git-commit-timestamp

  resourcetemplates:
    - apiVersion: tekton.dev/v1beta1
      kind: PipelineRun
      metadata:
        generateName: my-app-build-
      spec:
        pipelineRef:
          name: build-and-push-pipeline
        params:
          - name: revision
            value: $(tt.params.git-revision)
          - name: url
            value: $(tt.params.git-repo-url)
        workspaces:
          - name: source
            emptyDir: {}
```

#### Trigger

### Compatibility

When the `TriggerTemplate` bound to `TriggerBinding` is used as a pipelined execution template, the variable write is replaced with a concrete default value.

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: Trigger
metadata:
  name: my-github-trigger
spec:
  bindings:
    - ref: gitlab-push
      kind: ClusterTriggerBinding
  template:
    ref: my-app-build-template # Use the template associated with the above binding
  interceptors:
    - ref:
        name: "github"
      params:
        - name: "secretRef"
          value:
            secretName: github-secret
            secretKey: secretToken
        - name: "eventTypes"
          value: ["push"]
```

## Design Evaluation

### Reusability

- `TriggerTemplate` can be reused across multiple `Trigger`
- Parameterization allows for customization while maintaining consistency

### Simplicity

- Uses existing `TriggerTemplate` resources without API changes, leveraging familiar structure
- Clear labeling conventions (`triggertemplate.triggers.tekton.dev/bindings`) for easy identification
- Standardized annotation conventions (`tekton.dev/displayName`, `tekton.dev/description`) for metadata
- Single resource template limitation simplifies configuration and reduces complexity

### Consistency

- Standardized configuration patterns across task and pipeline executions
- Reduces configuration errors through templating and validation
- Ensures consistent security settings, resource allocations, and execution environments
- Clear template selection rules prevent ambiguity in configuration resolution

### User Experience

- Eliminates repetitive runtime configuration work for Trigger
- Trigger can be managed based on triggerTemplate
- Clear labeling and annotation conventions improve discoverability and documentation
- Maintains backward compatibility with existing TriggerTemplate usage
- Human-readable display names and descriptions enhance template management

### Performance

- No additional API overhead since existing TriggerTemplate resources are reused
- Efficient template resolution through Kubernetes label-based filtering
- Minimal impact on existing trigger functionality due to clear separation of concerns
- Single resource template limitation reduces processing complexity
- Template merge rules are based on proven Kubernetes merge patterns

### Security

- The functions provided fulfill https encrypted access.
- Triggers do not have the right to read user information directly
- All the operations of the trigger resources to meet the audit requirements

## References

- [Tekton Triggers Documentation](https://tekton.dev/docs/triggers/)
- [Tekton Pipeline Documentation](https://tekton.dev/docs/pipelines/)
- [Kubernetes Labeling Best Practices](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/)
- API References
  - [TriggerTemplate API Reference](../apis/kubernetes_apis/triggers/triggertemplate.mdx)
  - [TriggerBinding API Reference](../apis/kubernetes_apis/triggers/triggerbinding.mdx)
  - [Trigger API Reference](../apis/kubernetes_apis/triggers/triggers.mdx)
