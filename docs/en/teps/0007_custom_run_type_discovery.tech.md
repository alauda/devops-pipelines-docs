---
title: CustomRun Type Discovery via ConfigMap
authors:
  - "@qingliu"
creation-date: 2025-12-02T00:00:00.000Z
last-updated: 2025-12-02T00:00:00.000Z
status: proposed
---

# TEP-0007: CustomRun Type Discovery via ConfigMap

## Summary

This document defines a standardized mechanism for frontend applications to discover available `CustomRun` types (such as `ApprovalRequest`, `NotificationTask`, etc.) through `ConfigMaps` stored in the `kube-public` namespace. This enables dynamic UI generation and type selection without hardcoding `CustomRun` types in the frontend.

## Motivation

### Background

With the introduction of various `CustomRun` types (e.g., `ApprovalRequest` for approval gates, future `NotificationTask` for notifications), the frontend needs a standardized way to:

1. Discover all available `CustomRun` types supported by the platform
2. Display human-readable names and descriptions in multiple languages
3. Filter and categorize `CustomRun` types for better user experience
4. Access documentation and examples for each type

Currently, there is no unified mechanism for frontend applications to query available `CustomRun` types. This leads to:

- Hardcoded type information in frontend code
- Difficult to extend with new `CustomRun` types
- Poor internationalization support
- Lack of metadata for UI rendering (icons, descriptions, etc.)

### Goals

- Define a standardized `ConfigMap` structure for exposing `CustomRun` type metadata
- Enable frontend applications to dynamically discover available `CustomRun` types via Kubernetes API
- Support internationalization (i18n) for display names and descriptions
- Provide rich metadata for UI rendering (icons, categories, tags, documentation links)
- Allow independent management of each `CustomRun` type's metadata

### Non-goals

- This document does not define the behavior or implementation of specific `CustomRun` types
- This document does not cover authentication or authorization for accessing `ConfigMaps`
- This document does not define the UI rendering logic in frontend applications

## Proposal

### Overview

Each `CustomRun` type publishes its metadata as an independent `ConfigMap` in the `kube-public` namespace. Frontend applications can query all available types using a label selector and render appropriate UI elements based on the metadata.

### ConfigMap Structure

#### Namespace and Naming Convention

- **Namespace**: `kube-public` (readable by all authenticated users)
- **Naming Convention**: `customrun-{category}-{lowercase-kind}`
  - `{category}`: Must match the value of `tekton.dev/category` label
  - `{lowercase-kind}`: Lowercase version of the `kind` field (e.g., `ApprovalRequest` → `approvalrequest`)
  - Examples:
    - `kind: ApprovalRequest` → `customrun-approval-approvalrequest`
    - `kind: NotificationTask` → `customrun-notification-notificationtask`

#### Labels

Labels are used for filtering and categorization:

```yaml
metadata:
  labels:
    # Core identifier (required) - used by frontend to filter all CustomRun types
    tekton.dev/custom-run-type: "true"

    # Category identifier (required) - used for filtering by category
    tekton.dev/category: "approval"
```

**Standard Categories**:
- `approval` - Approval gates and manual interventions
- `notification` - Notification and alerting tasks
- `integration` - External system integrations
- `deployment` - Deployment-specific operations
- `testing` - Testing and validation tasks
- `security` - Security scanning and compliance checks

**Note**: These are recommended standard categories for consistency. Custom categories can be defined as needed, but using standard categories improves discoverability and user experience.

#### Annotations

Annotations store all metadata fields, following the same pattern as Tekton Hub `Task` annotations:

**Required Annotations**:

| Annotation | Description | Example |
|------------|-------------|---------|
| `tekton.dev/displayName` | Display name (English) | `Approval Request` |
| `tekton.dev/displayName.zh` | Display name (Chinese) | `审批请求` |
| `tekton.dev/description` | Description (English) | `Manual and automated approval gates...` |
| `tekton.dev/description.zh` | Description (Chinese) | `流水线执行的手动和自动审批关卡` |

**Recommended Annotations**:

| Annotation | Description | Example |
|------------|-------------|---------|
| `tekton.dev/icon` | Base64-encoded SVG icon | `data:image/svg+xml;base64,...` |
| `tekton.dev/tags` | Comma-separated tags | `approval,manual,automated` |
| `tekton.dev/platforms` | Supported platforms | `linux/amd64,linux/arm64` |

**Optional Annotations**:

| Annotation | Description | Example |
|------------|-------------|---------|
| `tekton.dev/pipelines.minVersion` | Minimum Tekton Pipelines version | `0.50.0` |
| `tekton.dev/example` | Embedded YAML example (single example) | `apiVersion: tekton.dev/v1\nkind: Pipeline\n...` |
| `tekton.dev/examplesURL` | Examples documentation URL (English) | `https://docs.example.com/en/examples/...` |
| `tekton.dev/examplesURL.zh` | Examples documentation URL (Chinese) | `https://docs.example.com/zh/examples/...` |
| `tekton.dev/deprecated` | Deprecation status | `true` / `false` |
| `tekton.dev/deprecation.message` | Deprecation message (English) | `This type is deprecated...` |
| `tekton.dev/deprecation.message.zh` | Deprecation message (Chinese) | `此类型已弃用...` |
| `tekton.dev/deprecation.replacedBy` | Replacement type reference | `approval.alaudadevops.io/v2alpha1` |

#### Data Fields

Data fields contain only the core type identification information:

**Required Fields**:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `apiVersion` | string | `CustomRun`'s apiVersion | `approval.alaudadevops.io/v1alpha1` |
| `kind` | string | `CustomRun`'s kind | `ApprovalRequest` |
| `enabled` | string | Whether this type is enabled | `true` / `false` |

**Future Extensions**:

In future versions, the `data` section may be extended to include dynamic form schemas for `CustomRun` parameters, similar to how Tekton `Task` parameters work. This would allow frontend applications to automatically generate parameter input forms when users configure a `CustomRun` in their `Pipeline`.
This feature is not yet implemented but is planned for future iterations to improve the user experience when configuring `CustomRun` tasks in the `Pipeline` editor.

### Internationalization (i18n)

Localized fields use language suffixes:

- `.en` - English (default, can be omitted)
- `.zh` - Chinese

**Field Resolution Logic**:

Frontend applications should resolve localized fields with the following fallback mechanism:

1. Try user's language with suffix (e.g., `tekton.dev/displayName.zh` for Chinese users)
2. If not found, fall back to default field without suffix (e.g., `tekton.dev/displayName`)

This ensures that even if a specific language is not provided, the system gracefully falls back to English (the default). For example, if a Japanese user accesses the system but no `.ja` suffix is provided, the system will display the English version.

### Icon Handling

Icons must be specified as **Base64-encoded SVG** in annotations:

```yaml
metadata:
  annotations:
    tekton.dev/icon: "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIi..."
```

Frontend applications render the SVG directly.

## Complete Examples

### Minimal Example

This is the minimum required configuration for a `CustomRun` type `ConfigMap`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: customrun-approval-simpleapproval
  namespace: kube-public
  labels:
    tekton.dev/custom-run-type: "true"
    tekton.dev/category: "approval"
  annotations:
    tekton.dev/displayName: "Simple Approval"
    tekton.dev/displayName.zh: "简单审批"
    tekton.dev/description: "A minimal approval example"
    tekton.dev/description.zh: "最小审批示例"
data:
  apiVersion: "approval.alaudadevops.io/v1alpha1"
  kind: "SimpleApproval"
  enabled: "true"
```

### Example 1: ApprovalRequest ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: customrun-approval-approvalrequest
  namespace: kube-public
  labels:
    tekton.dev/custom-run-type: "true"
    tekton.dev/category: "approval"
  annotations:
    # ===== Required Annotations =====
    # Display Name (i18n)
    tekton.dev/displayName: "Approval Request"
    tekton.dev/displayName.zh: "审批请求"

    # Description (i18n)
    tekton.dev/description: "Manual and automated approval gates for pipeline execution. Supports OpenShift Pipelines ApprovalTask integration and external approval systems (Jira, Email, Custom Script)."
    tekton.dev/description.zh: "流水线执行的手动和自动审批关卡。支持 OpenShift Pipelines ApprovalTask 集成和外部审批系统（Jira、邮件、自定义脚本）。"

    # ===== Recommended Annotations =====
    # Base64-encoded SVG icon
    tekton.dev/icon: "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzBweCIgaGVpZ2h0PSIzMHB4IiB2aWV3Qm94PSIwIDAgMzAgMzAiIHZlcnNpb249IjEuMSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8Y2lyY2xlIGN4PSIxNSIgY3k9IjE1IiByPSIxMCIgZmlsbD0iIzRDQUY1MCIvPgogIDxwYXRoIGQ9Ik0xMiAxNWwzIDMgNi02IiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIGZpbGw9Im5vbmUiLz4KPC9zdmc+"

    # Tags
    tekton.dev/tags: "approval,manual,automated,jira,email,gate"

    # Platforms
    tekton.dev/platforms: "linux/amd64,linux/arm64"

    # ===== Optional Annotations =====
    # Minimum Tekton Pipelines version
    tekton.dev/pipelines.minVersion: "0.50.0"

    # Embedded YAML example
    tekton.dev/example: |
      apiVersion: tekton.dev/v1
      kind: Pipeline
      metadata:
        name: example-approval-pipeline
      spec:
        tasks:
          - name: approval-gate
            taskRef:
              apiVersion: approval.alaudadevops.io/v1alpha1
              kind: ApprovalRequest
            params:
              - name: approvers
                value: ["admin", "group:ops-team"]

    # Examples documentation URLs (i18n)
    tekton.dev/examplesURL: "https://docs.example.com/en/examples/approval"
    tekton.dev/examplesURL.zh: "https://docs.example.com/zh/examples/approval"
data:
  # Core type identification only
  apiVersion: "approval.alaudadevops.io/v1alpha1"
  kind: "ApprovalRequest"
  enabled: "true"
```

### Example 2: Future NotificationTask ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: customrun-notification-notificationtask
  namespace: kube-public
  labels:
    tekton.dev/custom-run-type: "true"
    tekton.dev/category: "notification"
  annotations:
    tekton.dev/displayName: "Notification Task"
    tekton.dev/displayName.zh: "通知任务"

    tekton.dev/description: "Send notifications to external systems (Slack, Email, Webhook) during pipeline execution."
    tekton.dev/description.zh: "在流水线执行过程中向外部系统（Slack、邮件、Webhook）发送通知。"

    tekton.dev/icon: "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzBweCIgaGVpZ2h0PSIzMHB4IiB2aWV3Qm94PSIwIDAgMzAgMzAiIHZlcnNpb249IjEuMSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8cGF0aCBkPSJNMTUgNWMtMyAwLTUgMi01IDV2NWwtMyAzdjJoMTZ2LTJsLTMtM3YtNWMwLTMtMi01LTUtNXptMCAxOGMxLjEgMCAyLS45IDItMmgtNGMwIDEuMSAuOSAyIDIgMnoiIGZpbGw9IiNGRjk4MDAiLz4KPC9zdmc+"

    tekton.dev/tags: "notification,alert,slack,email,webhook"
    tekton.dev/platforms: "linux/amd64,linux/arm64"
data:
  apiVersion: "notification.alaudadevops.io/v1alpha1"
  kind: "NotificationTask"
  enabled: "true"
```

## Querying Available CustomRun Types

Frontend applications can query all `CustomRun` types using the Kubernetes API:

```bash
# Get all CustomRun types
kubectl get configmap -n kube-public -l tekton.dev/custom-run-type=true

# Get all approval types
kubectl get configmap -n kube-public -l tekton.dev/category=approval

# Get a specific type
kubectl get configmap customrun-approval-approvalrequest -n kube-public -o yaml
```

## Usage in Pipeline Definitions

Once frontend discovers available `CustomRun` types, users can use them in `Pipeline` definitions.

**Note**: The `apiVersion` and `kind` values in the `taskRef` section correspond directly to the `data.apiVersion` and `data.kind` fields from the `ConfigMap`. The frontend reads these values from the `ConfigMap` and populates them into the `Pipeline` YAML when the user selects a `CustomRun` type.

```yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: deploy-with-approval
spec:
  tasks:
    - name: build
      taskRef:
        name: build-image

    - name: approval-gate
      runAfter:
        - build
      taskRef:
        # These values come from ConfigMap data.apiVersion and data.kind
        apiVersion: approval.alaudadevops.io/v1alpha1
        kind: ApprovalRequest
      params:
        - name: approvers
          value:
            - admin
            - group:ops-team

    - name: deploy
      runAfter:
        - approval-gate
      taskRef:
        name: deploy-to-production
```

## Implementation Guidelines

### For CustomRun Type Developers

When developing a new `CustomRun` type:

1. Create a `ConfigMap` in `kube-public` namespace following the naming convention
2. Add required labels: `tekton.dev/custom-run-type`, `tekton.dev/category`
3. Provide required annotations: `tekton.dev/displayName`, `tekton.dev/displayName.zh`, `tekton.dev/description`, `tekton.dev/description.zh`
4. Include recommended annotations: `tekton.dev/icon` (Base64 SVG), `tekton.dev/tags`, `tekton.dev/platforms`
5. Set core identification in data: `apiVersion`, `kind`, `enabled`

### For Operators

When deploying `CustomRun` type support:

1. Ensure the `ConfigMap` is created in `kube-public` namespace during installation
2. Update the `ConfigMap` when the `CustomRun` type is upgraded
3. Set `enabled: "false"` in data to temporarily disable a type without deleting the `ConfigMap`
4. Mark deprecated types with `tekton.dev/deprecated: "true"` annotation and provide migration guidance
5. Monitor for deprecated types and plan migrations

### For Frontend Developers

When implementing `CustomRun` type discovery:

1. Query `ConfigMaps` using label selector `tekton.dev/custom-run-type=true`
2. Filter by category using `tekton.dev/category` label if needed
3. Respect the `enabled` field in data and hide disabled types
4. Implement proper i18n field resolution based on user locale (`.zh` suffix for Chinese, fall back to default for English)
5. Handle missing optional annotations gracefully
6. Cache `ConfigMap` data and refresh periodically
7. Validate and sanitize icon SVG data to prevent XSS attacks
8. Validate URL annotations (e.g., `examplesURL`) before rendering as links
9. Parse and display embedded YAML examples from `example` annotation when available

## Design Rationale

### Why ConfigMaps in kube-public?

- **Accessibility**: All authenticated users can read from `kube-public` namespace
- **Standard Kubernetes Resource**: No custom API or controller required
- **Easy to Manage**: Operators can easily create/update `ConfigMaps` using standard tools
- **Namespace Isolation**: Separating metadata from implementation keeps concerns separated

### Why Independent ConfigMaps per Type?

- **Independent Management**: Each `CustomRun` type can be managed independently
- **No Conflicts**: Updates to one type don't affect others
- **Clear Ownership**: Each `ConfigMap` can have its own RBAC and ownership
- **Easier Rollback**: Can rollback individual type metadata without affecting others

### Why Put Metadata in Annotations Instead of Data?

- **Consistency with Tekton Hub**: Follows the same pattern as Tekton Hub `Task` annotations
- **Annotation Key Flexibility**: Annotations support `/` character, allowing proper namespacing (e.g., `tekton.dev/displayName`)
- **Data Simplicity**: Keeps data section minimal with only core identification fields
- **Separation of Concerns**: Annotations for metadata, data for core type information

### Why Only Base64-Encoded SVG for Icons?

- **Consistency**: Single standardized format across all types
- **Self-Contained**: No external dependencies for icon rendering
- **Customization**: Full control over icon appearance and branding
- **Security**: Frontend can validate SVG content before rendering

## Migration and Compatibility

### Initial Rollout

- Create `ConfigMaps` for existing `CustomRun` types (`ApprovalRequest`)
- Frontend gradually adopts the discovery mechanism
- Legacy hardcoded types coexist with discovered types during transition

### Future Evolution

- New `CustomRun` types automatically become available to frontend when `ConfigMap` is created
- Schema versioning (future TEP) may introduce new required annotations
- Deprecated types can be marked with `tekton.dev/deprecated: "true"` before removal
- **Parameter Schema Support**: Future versions may add dynamic form schema definitions in the `data` section to enable automatic parameter form generation in the frontend, similar to how Tekton `Task` parameters are handled. This will allow users to configure `CustomRun` parameters through a user-friendly form interface rather than writing YAML manually.

## Security Considerations

- `ConfigMaps` in `kube-public` are **readable by all authenticated users**
- Do not store sensitive information in these `ConfigMaps`
- Icon base64 data should be validated to prevent XSS attacks in frontend
- URL annotations (e.g., `examplesURL`) should be validated before rendering as links
- Embedded YAML examples in `example` annotation should be parsed safely to prevent code injection
- Frontend should sanitize all user-facing content from `ConfigMaps`

## References

- [Kubernetes ConfigMap Documentation](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes Standard Labels](https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/)
- [Kubernetes Annotations](https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/)
- [TEP-0006: Approval Capabilities Research](./0006_approval_capabilities.tech.md)
