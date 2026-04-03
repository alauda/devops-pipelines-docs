---
title: GitLab Events as ClusterTriggerBindings
authors:
  - '@alaudadevops'
creation-date: 2025-01-13T00:00:00.000Z
last-updated: 2025-01-13T00:00:00.000Z
status: proposed
sourceSHA: 752b6584abe05a2216750beaf05ba5938cdfd2b02f2089f9f8980f071267596f
---

# TEP-0002: GitLab Events as ClusterTriggerBindings

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
- [Alternatives](#alternatives)
- [Implementation Plan](#implementation-plan)
- [References](#references)

<!-- /toc -->

## Summary

This proposal aims to provide standardized ClusterTriggerBindings for GitLab events to achieve compatibility with OpenShift Pipelines and simplify migrations between ACP (Alauda Container Platform). These bindings will cover the most commonly used GitLab events, including merge requests, pushes, and comment events.

## Motivation

Currently, users need to reconfigure their GitLab trigger bindings when migrating between different platforms. By providing standardized ClusterTriggerBindings, we can ensure a consistent experience in OpenShift and ACP environments and reduce configuration work.

### Goals

- Provide GitLab event ClusterTriggerBindings compatible with OpenShift Pipelines.
- Support the most commonly used GitLab event types.
- Simplify the migration process between OpenShift and ACP.
- Ensure consistency and predictability in bindings.

### Non-Goals

- Support all possible GitLab webhook events.
- Provide custom bindings for specific use cases.
- Modify the existing GitLab webhook format.

### Use Cases

1. Platform migration
    - Users can seamlessly migrate their CI/CD pipelines between OpenShift and ACP.
    - Existing trigger configurations can be used directly without modification.

2. Standardized configuration
    - Teams can use the same trigger configurations in different environments.
    - Reduces configuration errors and inconsistencies.

### Requirements

- Must support the following GitLab event types:
    - Merge Request events
    - Push events
    - Comment events (including comments on issues, merge requests, commits, and snippets)
- Bindings must be fully compatible with GitLab webhook formats.
- Bindings must provide sufficient parameters to support common CI/CD use cases.

## Research and Analysis

Research and analysis were conducted on the event handling of OpenShift's GitHub and GitLab to identify suitable event solutions.

### OpenShift GitLab Bindings

### Merge Request Event Binding

**pull/merge_request event**: <https://docs.gitlab.com/ee/user/project/integrations/webhooks.html#merge-request-events>

#### Merge Request Payload

```json
{
  "object_kind": "merge_request",
  "event_type": "merge_request",
  "user": {
    "id": 1,
    "name": "Administrator",
    ...
  },
  "project": {
    "id": 1,
    "name": "hello-trigger",
    ...
  },
  "object_attributes": {
    "assignee_id": null,
    "author_id": 1,
    ...
  },
  "labels": [],
  "changes": {
    "state_id": {
      "previous": 2,
      "current": 1
    },
    "updated_at": {
      "previous": "2025-01-17 05:36:59 UTC",
      "current": "2025-01-17 05:37:28 UTC"
    }
  },
  "repository": {
    "name": "hello-trigger",
    ...
  }
}
```

#### Merge Request TriggerBinding

```yaml
apiVersion: triggers.tekton.dev/v1alpha1
kind: ClusterTriggerBinding
metadata:
  name: gitlab-mergereq
spec:
  params:
  - name: git-repo-url
    value: $(body.project.git_http_url)
  - name: mergereq-sha
    value: $(body.object_attributes.last_commit.id)
  - name: mergereq-action
    value: $(body.object_attributes.action)
  - name: mergereq-number
    value: $(body.object_attributes.iid)
  - name: mergereq-repo-name
    value: $(body.repository.name)
  - name: mergereq-url
    value: $(body.object_attributes.url)
  - name: mergereq-title
    value: $(body.object_attributes.title)
```

### Push Event

**push events:** <https://docs.gitlab.com/ee/user/project/integrations/webhooks.html#push-events>

#### Push Payload

```json
{
  "object_kind": "push",
  "event_name": "push",
  ...
}
```

#### Push TriggerBinding

```yaml
apiVersion: triggers.tekton.dev/v1alpha1
kind: ClusterTriggerBinding
metadata:
  name: gitlab-push
  labels:
    cpaas.io/tool: gitlab
  annotations:
    ui.cpaas.io/icon: data:image/svg+xml;base64,...
spec:
  params:
  - name: git-revision
    value: $(body.checkout_sha)
  - name: git-commit-message
    value: $(body.commits[0].message)
  - name: git-repo-url
    value: $(body.repository.git_http_url)
  - name: git-repo-name
    value: $(body.repository.name)
  - name: pusher-name
    value: $(body.user_name)
```

### Comment Event

**comment events are done at commit, merge_request, issue and code snippet for more info**: <https://docs.gitlab.com/ee/user/project/integrations/webhooks.html#comment-events>

```json
{
  "object_kind": "note",
  ...
}
```

#### Merge Request Comment TriggerBinding

```yaml
apiVersion: triggers.tekton.dev/v1alpha1
kind: ClusterTriggerBinding
metadata:
  name: gitlab-review-comment-on-mergerequest
  labels:
    cpaas.io/tool: gitlab
  annotations:
    ui.cpaas.io/icon: data:image/svg+xml;base64,...
spec:
  params:
    - name: mergereq-url
      value: $(body.merge_request.url)
    - name: comment-description
      value: $(body.object_attributes.description)
    - name: comment-url
      value: $(body.object_attributes.url)
    - name: mr-owner
      value: $(body.user.name)
```

#### Issue Comment TriggerBinding

```yaml
apiVersion: triggers.tekton.dev/v1alpha1
kind: ClusterTriggerBinding
metadata:
  name: gitlab-review-comment-on-issues
  labels:
    cpaas.io/tool: gitlab
  annotations:
    ui.cpaas.io/icon: data:image/svg+xml;base64,...
spec:
  params:
  - name: issue-url
    value: $(body.issue.url)
  - name: issue-title
    value: $(body.issue.title)
  - name: issue-comment-link
    value: $(body.object_attributes.url)
  - name: issue-owner
    value: $(body.user.name)
```

## Proposal

Implement five ClusterTriggerBindings:

1. `gitlab-mergereq`: Handles merge request events.
2. `gitlab-push`: Handles push events.
3. `gitlab-review-comment-on-issues`: Handles issue comments.
4. `gitlab-review-comment-on-mergerequest`: Handles merge request comments.
5. `gitlab-review-comment-on-commit`: Handles commit comments.
6. `gitlab-review-comment-on-snippet`: Handles snippet comments.

### Notes and Caveats

- The binding names should remain consistent with OpenShift Pipelines to ensure compatibility.
- Some events may contain large amounts of data; parameters should be used cautiously to avoid performance issues.
- Users can still create custom bindings to extend functionalities.

## Design Details

The design philosophy:

- Reuse field names as much as possible.
- Analyze multiple repositories and unify core fields, such as `revision` and `repo-url`.

### GitLab Event Analyses

#### Merge Request TriggerBinding

*Note: keeping only the params for brevity*

```yaml
spec:
  params:
    ## event meta
    - name: event-type
      value: $(body.event_type)
    ## project
    ...
    ## merge request
    - name: mergereq-sha
      value: $(body.object_attributes.last_commit.id)
```

#### Push TriggerBinding

```yaml
spec:
  params:
    ## event meta
    - name: event-type
      value: $(body.event_type)
    ...
    ## push
    - name: git-revision
      value: $(body.ref)
```

### Design Evaluation

#### Reusability

- The bindings will be usable in any Tekton Triggers-supporting environment.
- Compatibility with OpenShift Pipelines facilitates migration.

#### Simplicity

- Utilizes standard webhook formats.
- Clear naming conventions for parameters.
- Minimizes configuration requirements.

#### User Experience

- Seamless migration experience.
- Consistent configuration approaches.
- Pre-defined common parameters.

#### Performance

- Minimizes parameter sets to optimize performance.
- Avoids unnecessary data extraction.

## Alternatives

1. Custom Bindings
    - Allow users to create their own bindings.
    - Cons may include inconsistent configuration and difficult migration.

2. Generic Bindings
    - Create a more generic binding format.
    - Cons may include insufficient specificity and increased configuration needs.

## Implementation Plan

### Test Plan

1. Integration Tests

Test integration with GitLab webhook payloads: Validate Bindings with various payloads.

### Upgrade and Migration Strategy

1. Documentation
    - Provide detailed migration guidance.
    - Include example configurations.

2. Version Control
    - Follow semantic versioning.
    - Maintain backward compatibility.

## References

- [GitLab Webhook Documentation](https://docs.gitlab.com/ee/user/project/integrations/webhooks.html)
- [Tekton Triggers Documentation](https://tekton.dev/docs/triggers/)
- [OpenShift Pipelines Documentation](https://docs.openshift.com/container-platform/latest/cicd/pipelines/understanding-openshift-pipelines.html)
- [OCP GitLab Events](https://github.com/openshift-pipelines/operator/blob/main/upstream/cmd/openshift/operator/kodata/tekton-addon/addons/01-clustertriggerbindings/gitlab.yaml)
