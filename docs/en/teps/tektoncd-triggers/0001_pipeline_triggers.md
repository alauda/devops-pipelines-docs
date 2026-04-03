---
title: Pipeline Trigger Technical Design Proposal
date: '2024-12-31'
draft: true
sourceSHA: 4bf0f77ef9006b15e989bddeaa56b9258a037297293f21928d977e5af6be6076
---

- [Overview](#overview)
- [Motivation](#motivation)
  - [Objectives](#objectives)
  - [Non-objectives](#non-objectives)
  - [Use Cases](#use-cases)
  - [Requirements](#requirements)
- [Proposal](#proposal)
  - [Considerations and Warnings](#considerations-and-warnings)
- [Design Details](#design-details)
  - [Event Types (ClusterTriggerBinding and TriggerBinding)](#event-types-clustertriggerbinding-and-triggerbinding)
  - [Interceptors (ClusterInterceptors and Interceptors)](#interceptors-clusterinterceptors-and-interceptors)
    - [Cel Interceptor](#cel-interceptor)
  - [Triggers (Trigger)](#triggers-trigger)
    - [Pipeline Trigger](#pipeline-trigger)
  - [EventListener](#eventlistener)
    - [NodePort](#nodeport)
    - [Ingress + TLS Deployment](#ingress--tls-deployment)
    - [HTTPS NodePort Deployment](#https-nodeport-deployment)
    - [Small-scale Configuration Plan](#small-scale-configuration-plan)
  - [EventListener Save and Retrieval Plan](#eventlistener-save-and-retrieval-plan)
- [Design Evaluation](#design-evaluation)
  - [Reusability](#reusability)
  - [Simplicity](#simplicity)
  - [Flexibility](#flexibility)
  - [Consistency](#consistency)
  - [User Experience](#user-experience)
  - [Performance](#performance)
  - [Risks and Mitigations](#risks-and-mitigations)
  - [Disadvantages](#disadvantages)
- [Alternatives](#alternatives)
- [Implementation Plan](#implementation-plan)
  - [Testing Plan](#testing-plan)
  - [Required Infrastructure](#required-infrastructure)
  - [Upgrade and Migration Strategy](#upgrade-and-migration-strategy)
  - [Implementation Pull Requests](#implementation-pull-requests)
- [References](#references)

## Overview

To help users quickly create Tekton Triggers while reusing existing mechanisms and capabilities.

## Motivation

The Tekton Trigger API and its capabilities are very flexible, supporting a wide range of scenarios. In the product, we need to guide users on how to quickly create triggers and automatically trigger pipelines through the experience.

### Objectives

- Provide guidance on how to create triggers through product experience.
- Assist product developers and platform teams in supporting more event types.

### Non-objectives

- Automating the operational deployment of triggers.
- Addressing all UI experience packaging related to triggers.

### Use Cases

Typically, the individuals creating pipeline triggers are either pipeline users or developers, so the core issues to resolve involve the following roles:

- `Namespace Developers` or `Namespace Administrators`

The experience should consider the most common use cases and deliver a universal experience that is satisfactory but does not include specific implementations:

- `Code Repository Trigger`: Triggered by code repository changes, PR changes, or code Tag triggers.
- `Artifact Trigger`: Triggered when an artifact changes.

### Requirements

The following conditions must be met:

- Utilize existing Tekton Triggers APIs.
- Not depend on the deployment of EventListeners for each trigger.
- Support the native API capabilities of Triggers.
- Support both platform-provided and user-defined events while enabling users to easily identify the tools/platforms/products being used.
- Allow users to define custom event filtering criteria.
- Enable the use of information from events as pipeline parameters.

## Proposal

By reusing existing Tekton Triggers APIs and providing a simplified and unified experience, we aim to allow users to quickly add required triggers while maintaining a flexible YAML creation entry to satisfy scenarios beyond form experiences.

EventListener (Webhook event entry) will be the responsibility of the operational or platform teams for deployment and maintenance, while the product will provide various deployment configuration examples to ensure operational success.

### Considerations and Warnings

The approach taken considers developers as primary maintainers of triggers, with foundational webhook settings configured by the platform team or operations team. This may introduce the following potential issues:

- The platform team/operators may be unaware of what needs to be prepared in advance or unclear about how to configure it.
- Developers may find themselves with no EventListener available to handle Triggers before or after the creation of triggers, rendering the triggers unusable.

The proposal will attempt to resolve these issues.

## Design Details

### Event Types (ClusterTriggerBinding and TriggerBinding)

Tool types and icon issues are addressed by setting the following fields:

**Display the corresponding tool's icon:**

- `metadata.annotations.ui.cpaas.io/icon`: `<base64 image svg / png>`

**Support filtering by tool:**

- `metadata.labels.cpaas.io/tool`: `<tool/product name>`

**TriggerBinding fields:**

- `spec.params`: (array) Declare parameters parsed from events and output as variables. Please refer to the [TriggerBinding documentation](https://tekton.dev/vault/triggers-v0.26.x-lts/triggerbindings/#accessing-data-in-http-json-payloads).

Using `Github`, an example is as follows:

```yaml
apiVersion: triggers.tekton.dev/v1alpha1
kind: ClusterTriggerBinding
metadata:
  annotations:
    ui.cpaas.io/icon: data:image/svg+xml;base64,PD94bWwgdm[...]
  labels:
    cpaas.io/tool: github
  name: github-pullrequest
spec:
  params:
  - name: git-repo-url
    value: $(body.repository.html_url)
  - name: pullreq-sha
    value: $(body.pull_request.head.sha)
  - name: pullreq-action
    value: $(body.action)
  - name: pullreq-number
    value: $(body.number)
  - name: pullreq-repo-full_name
    value: $(body.repository.full_name)
  - name: pullreq-html-url
    value: $(body.pull_request.html_url)
  - name: pullreq-title
    value: $(body.pull_request.title)
  - name: pullreq-issue-url
    value: $(body.pull_request.issue_url)
  - name: organisations-url
    value: $(body.pull_request.user.organizations_url)
  - name: user-type
    value: $(body.pull_request.user.type)
```

### Interceptors (ClusterInterceptors and Interceptors)

ClusterInterceptors and Interceptors in Tekton Triggers are components designed to handle and filter incoming events. They process events before reaching the trigger.

ClusterInterceptors are cluster-wide interceptors that can be used across all namespaces in the cluster, whereas Interceptors are namespace-level interceptors used only within specific namespaces.

The primary functions of interceptors include:

- Validating the authenticity of events (e.g., validating Webhook signatures).
- Filtering events (determining whether to trigger a pipeline based on event content).
- Modifying or enhancing event content (adding or transforming event data).
- Standardizing event formats from different sources.

Interceptors work by processing raw events and returning a processed event body. If an interceptor determines that an event should not trigger a pipeline, it can reject the event directly.

Tekton Triggers come with the following default `ClusterInterceptors`:

1. **Bitbucket Interceptor**: Handles Webhook events from Bitbucket, validates event signatures, and extracts relevant information. Supports both Bitbucket Cloud and Bitbucket Server.

2. **Cel Interceptor**: A general-purpose expression language interceptor allowing custom event filtering and transformation logic using CEL (Common Expression Language).

3. **GitHub Interceptor**: Processes GitHub Webhook events, validates event signatures, and extracts GitHub-related event data.

4. **GitLab Interceptor**: Handles GitLab Webhook events, validates event signatures, and extracts GitLab-specific event information.

Note: The above are the default ClusterInterceptors provided in Tekton Triggers v0.26.x. Each interceptor is designed to handle Webhook events from specific sources, providing event validation and data extraction capabilities.

#### Cel Interceptor

In Tekton Triggers, the CEL (Common Expression Language) interceptor is a powerful generic interceptor that allows users to filter and transform event data using CEL expressions. The CEL interceptor supports the following parameters:

- `filter`: A CEL expression used to filter events. The expression must return a boolean value; if it returns false, the event will be rejected.
- `overlays`: A set of CEL expressions used to modify or add data. Each overlay includes:
  - `key`: The name of the new data field.
  - `expression`: The CEL expression used to generate the new data.
- `matchContext`: CEL expressions used to match the request context, accessing request headers, URLs, etc.

Here is an example using the CEL interceptor:

```yaml
[...]
spec:
  interceptors:
    - ref:
        name: "cel"
      params:
        - name: "filter"
          value: "header.match('X-GitHub-Event', 'pull_request')"
        - name: "overlays"
          value:
            - key: extensions.truncated_sha
              expression: "body.pull_request.head.sha.truncate(7)"
[...]
```

### Triggers (Trigger)

Configuring triggers is a routine task for developers to automate the triggering of pipelines.

In OpenShift, the thinking behind triggers is to create an EventListener directly (as illustrated below). However, because EventListener involves numerous network and runtime configurations, it's believed that we should maintain trigger-related configurations directly using Tekton's native `Trigger` resource and shift the deployment and maintenance of EventListener to the platform team's responsibilities.

The Trigger resource is divided into the following fields:

- `interceptors`: (array, optional) Set one or more Interceptors to handle the event payload before passing it to the `TriggerTemplate`.
- `bindings`: (array) Define a set of event information bindings referencing (from ClusterTriggerBinding or TriggerBinding APIs) or declare embedded definitions using key/value arrays.
- `template`: Declare a reference to a TriggerTemplate or an embedded definition.
- `serviceAccountName`: (optional) Provide the specific ServiceAccount used by the EventListener to create target resources.

#### Pipeline Trigger

Using the Trigger resource.

**Basic Information:**

- Name: `metadata.name`
- Description: `metadata.annotations.cpaas.io/description`
- Labels: `metadata.labels`
- Annotations: `metadata.annotations`

Note: For a trigger associated with a specific pipeline, the following label must be added to labels: `tekton.dev/pipeline: <pipeline name>` to mark the trigger belonging to that pipeline.

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: Trigger
metadata:
  name: trigger # Name
  labels: {} # Labels
  annotations: # Annotations
    cpaas.io/description: "description" # Description
```

**Event:**

- Events: (array, multi-select) from the `ClusterTriggerBinding` API; use `metadata.name` to fill in `spec.bindings[].ref` and write `spec.bindings[].kind` as `ClusterTriggerBinding`. Support for namespace-based `TriggerBinding` forms will be considered later.
- Interceptors: (array, optional) `spec.interceptors[]`
  - Interceptors: From the `ClusterInterceptor` API, fill in `metadata.name` to `spec.interceptors[].ref.name`. Support for namespace-based `Interceptor` form support will be considered later.
  - Name: (optional) The name of the interceptor in the trigger, of type string.
  - Parameters: (array, optional) `spec.interceptors[].params`
    - Key: Parameter name, of type string `spec.interceptors[].params[].name`.
    - Value: The required value for the parameter, of type YAML `spec.interceptors[].params[].value`.

      ```yaml
    apiVersion: triggers.tekton.dev/v1beta1
    kind: Trigger
    metadata:
      name: trigger # Name
    spec:
      bindings: # Event
        - ref: github # ClusterTriggerBinding name
          kind: ClusterTriggerBinding
      interceptors: # Group of interceptors
        - ref:
            name: "cel" # Interceptor, ClusterInterceptor name
          name: "branch filter" # Name, string
          params: # Interceptor parameters, optional
          - name: filter # Parameter key, string
            value: "body.action in ['opened', 'reopened']" # Parameter value, YAML
    ```

**Pipeline:**

- Pipeline: Select a `Pipeline` in the same namespace.
- Parameters: From the selected `Pipeline`.
- Workspaces: From the selected `Pipeline`.

Use the `spec.template.spec` field to declare the pipeline template:

- `params`: Declare the parameters supported by the pipeline template, which can be directly copied from the selected `ClusterTriggerBinding`.
- `resourcetemplates`: Store `PipelineRun` content, which can use the parameters in `params` format as `$(tt.params.<param name>)`, along with supported variable formats after `<param name>`, such as using an `object`'s `abc` field as `$(tt.params.object.abc)`.

  ```yaml
  apiVersion: triggers.tekton.dev/v1beta1
  kind: Trigger
  metadata:
    name: trigger # Name
  spec:
    template: # Pipeline (Template)
    spec: # TriggerTemplate spec
      params: # Parameters supported by the pipeline template, names come from TriggerBinding
        - name: commit
          type: string
      resourcetemplates: # Definition of the pipeline execution record (Template)
        - apiVersion: tekton.dev/v1
          kind: PipelineRun
          metadata:
            generateName: <pipeline name>-
            labels:
              tekton.dev/pipeline: <pipeline name> # Pipeline property label
          spec:
            pipelineRef: # Pipeline resource reference
              name: <pipeline name>
            params:  # Pipeline parameters, values can be displayed and used with above parameters
              - name: my-param
                value: $(tt.params.commit)
            workspaces: # Pipeline workspaces
              - name: source
                emptyDir: {}
  ```

Note: In OpenShift Pipelines, `params` are directly copied from `TriggerBinding`, and users can re-enter various variables in the parameter forms, such as `$(tt.params.abc)`.

**Complete Example:**

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: Trigger
metadata:
  name: trigger # Name
  labels: {} # Labels
  annotations: {} # Annotations
spec:
  name: "description" # Description (to be verified)
  bindings: # Event
    - ref: github # ClusterTriggerBinding name
      kind: ClusterTriggerBinding
  interceptors: # Group of interceptors
    - ref:
        name: "cel" # Interceptor, ClusterInterceptor name
      name: "branch filter" # Name, string
      params: # Interceptor parameters, optional
      - name: filter # Parameter key, string
        value: "body.action in ['opened', 'reopened']" # Parameter value, YAML
  template: # Pipeline (Template)
    spec: # TriggerTemplate spec
      params: # Parameters supported by the pipeline template, names come from TriggerBinding
        - name: commit
          type: string
      resourcetemplates: # Definition of pipeline execution records (Templates)
        - apiVersion: tekton.dev/v1
          kind: PipelineRun
          metadata:
            generateName: <pipeline name>-
            labels:
              tekton.dev/pipeline: <pipeline name> # Pipeline property label
          spec:
            pipelineRef: # Pipeline resource reference
              name: <pipeline name>
            params:  # Pipeline parameters, values can be displayed and used with above parameters
              - name: my-param
                value: $(tt.params.commit)
            workspaces: # Pipeline workspaces
              - name: source
                emptyDir: {}
```

### EventListener

Due to the involvement of network and infrastructure configurations, the maintenance of EventListener needs to adapt based on the scale of the planned deployment, taking into account the available infrastructure capabilities as follows to consider different solutions:

**Infrastructure Capabilities:**

- NodePort HTTP address (simple, fast, insecure)
- Self-signed TLS certificate + Ingress + Address/DNS (simple, encrypted, compatibility with tools/webhook initiation needs to be considered)
- Official TLS certificate + Ingress + DNS (complex configuration, high foundational setup requirements, most secure)

#### NodePort

Deploy the EventListener service using NodePort to accept external requests.

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: EventListener
metadata:
  name: eventlistener
spec:
  serviceAccountName: "eventlistener" # Custom SA
  # Declaring Kubernetes resources, default is Deployment
  resources:
    kubernetesResource:
      serviceType: NodePort # NodePort service type
      servicePort: 80  # Service port (container port)
      spec: # Deployment spec
        template:
          metadata:
            labels: {} # Deployment labels
            annotations: {} # Deployment annotations
          spec:
            serviceAccountName: eventlistener # Unified as above SA
            nodeSelector: {} # Optional Node Selector
            tolerations: [] # Optional tolerations
```

#### Ingress + TLS Deployment

Use Ingress to resolve the usage of self-signed certificates or public certificates while deploying the EventListener service using NodePort. [Documentation](https://tekton.dev/vault/triggers-v0.26.x-lts/eventlisteners/#exposing-an-eventlistener-using-a-kubernetes-ingress-object)

TODO: To be verified

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: EventListener
metadata:
  name: eventlistener
spec:
  serviceAccountName: "eventlistener" # Custom SA
  # Declaring Kubernetes resources, default is Deployment
  resources:
    kubernetesResource:
      serviceType: NodePort # NodePort service type
      servicePort: 80  # Service port (container port)
      spec: # Deployment spec
        template:
          metadata:
            labels: {} # Deployment labels
            annotations: {} # Deployment annotations
          spec:
            [...]
```

Create an Ingress object, as shown below using Nginx Ingress class as an example:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: eventlistener-ingress
  annotations:
    kubernetes.io/ingress.class: "nginx"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - eventlistener.example.com
    secretName: eventlistener-tls-secret
  rules:
  - host: eventlistener.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: eventlistener
            port:
              number: 80
```

When using ALB, keep other configurations consistent while modifying the following `annotations` and `spec.ingressClassName`:

TODO: To be verified

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: eventlistener-ingress
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: "443" # TLS port
    nginx.ingress.kubernetes.io/proxy-body-size: "512m" # Payload size limit, this is 512MB
    nginx.ingress.kubernetes.io/proxy-read-timeout: "600" # Read timeout, in seconds
    nginx.ingress.kubernetes.io/proxy-connect-timeout: "15" # Connection timeout, in seconds
    nginx.ingress.kubernetes.io/service-upstream: "true" # TODO: Confirm
spec:
  ingressClassName: alb
```

If using a self-signed certificate, the following configurations should be added to Ingress and modify the TLS configuration in the ingress based on the secret name outputted from `Certificate`.

TODO: To be verified

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: eventlistener-ingress
  annotations:
    kubernetes.io/ingress.class: "nginx"
    cert-manager.io/cluster-issuer: "selfsigned-issuer"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rewrite-target: /
```

#### HTTPS NodePort Deployment

Deploy the EventListener service using an official or self-signed certificate. [Documentation](https://github.com/tektoncd/triggers/blob/release-v0.26.x/examples/v1beta1/eventlistener-tls-connection/README.md)

TODO: To be verified

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: EventListener
metadata:
  name: eventlistener
spec:
  serviceAccountName: "eventlistener" # Custom SA
  # Declaring Kubernetes resources, default is Deployment
  resources:
    kubernetesResource:
      serviceType: NodePort # NodePort service type
      servicePort: 80  # Service port (container port)
      spec: # Deployment spec
        template:
          metadata:
            labels: {} # Deployment labels
            annotations: {} # Deployment annotations
          spec:
            serviceAccountName: eventlistener # Unified as above SA
            containers: # Use TLS certificates via mounted secrets.
            - env:
              - name: TLS_CERT
                valueFrom:
                  secretKeyRef:
                    name: tls-secret-key
                    key: tls.crt
              - name: TLS_KEY
                valueFrom:
                  secretKeyRef:
                    name: tls-secret-key
                    key: tls.key
```

**Scale:**

- Small Scale: A small number of pipelines and triggers, 100 namespaces * 10 pipelines * 2 triggers.

#### Small-scale Configuration Plan

TODO: To be tested and verified.

Deploy a single or multiple instances of EventListener within a cluster to handle incoming webhooks/events and have the EventListener manage all `Triggers` within the cluster.

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: EventListener
metadata:
  name: eventlistener
spec:
  serviceAccountName: "eventlistener" # Custom SA
  namespaceSelector: # Responsible for triggers in all namespaces
    matchNames:
      - "*"
  resources:
    kubernetesResource:
      # Service example is NodePort.
      serviceType: NodePort
      servicePort: 80
      spec:
        template:
          metadata:
            labels: {} # Deployment labels
            annotations: # Deployment annotations
          spec:
            serviceAccountName: eventlistener # Unified as above SA
            [...] # Other configurations
```

### EventListener Save and Retrieval Plan

After deploying the EventListener, the access address needs to be manually saved.

TODO: Design and write.

## Design Evaluation

### Reusability

Not applicable.

### Simplicity

The design considers that users can place all necessary configurations in a single resource `Trigger`, eliminating the need to maintain multiple different resources simultaneously.

### Flexibility

The trigger maintenance methods do not restrict users from customizing the required trigger configurations via YAML, maintaining a high level of flexibility.

### Consistency

This proposal reuses the existing Tekton Triggers API, maintaining consistency.

### User Experience

By simplifying and unifying the maintenance of `Triggers` resources, the user experience becomes simpler while retaining the existing concepts.

### Performance

Refer to the "Risks and Mitigations" section below.

### Risks and Mitigations

**Risks:**

Because this solution involves a single EventListener handling multiple triggers, requiring a layer of filtering (Interceptors) within each trigger, there are several performance and usage risks:

- Excessive parallel processing of requests by the EventListener leading to performance and stability issues.
- Excessive parallel processing of requests by one or multiple interceptors leading to performance and stability issues.

**Mitigation Strategies:**

EventListener: Consider maintaining different EventListeners separately to spread out request volumes and reduce the load on individual instances. The following deployment models may be considered:

1. A dedicated EventListener for each project: To avoid uneven usage causing service quality issues. This measure is recommended for medium-scale operations.
2. A dedicated EventListener for each namespace: To address the load of maintaining each namespace separately. This is suggested for large-scale operations.
3. A dedicated EventListener for each pipeline: To address high loads on different pipelines. This is a rarely seen scenario, as the overall infrastructure maintenance cost is comparatively high.

Interceptor: Operated as a stateless service, scaling out different instances can distribute request numbers across multiple instances.

In larger scales, using interceptor services across different namespaces can mitigate the impact between projects.

### Disadvantages

TODO

## Alternatives

Individually maintaining each Tekton Triggers API to address specific use cases:

- Configure EventListeners in namespaces as needed, similar to OCP, where each trigger maintains its own EventListener + TriggerTemplate.
- Split each trigger into Trigger, TriggerTemplate, and related bindings.

## Implementation Plan

### Testing Plan

Consideration should be given to:

- Testing functionality in small-scale usage scenarios.
- Identifying the limits of the above solutions through non-functional testing.

### Required Infrastructure

When using Kubernetes clusters, one of the following infrastructure configurations is required:

- Direct access to a certain HTTP port of the cluster (NodePort): By opening several ports, operations teams can receive external requests. Note: No encryption.
- Use self-signed certificates and HTTPS Ingress: By using cert-manager or manually generating TLS certificates to provide domain names or ingress instance addresses for receiving events/webhooks. Note: There are risks in tool-side configurations; not all tools/platforms support ignoring or skipping TLS verification.
- Use official certificates and HTTPS Ingress (recommended): By configuring valid TLS certificates, Ingress service, and corresponding DNS resolution on the platform to securely accept webhooks.

### Upgrade and Migration Strategy

Not applicable.

### Implementation Pull Requests

TODO

## References

- [EventListener docs](https://tekton.dev/docs/triggers/eventlisteners)

From the perspective of OpenShift Pipelines, there have been no optimizations in this regard.

- [OCP GitHub Events](https://github.com/openshift-pipelines/operator/blob/main/upstream/cmd/openshift/operator/kodata/tekton-addon/addons/01-clustertriggerbindings/github.yaml)
- [OCP GitLab Events](https://github.com/openshift-pipelines/operator/blob/main/upstream/cmd/openshift/operator/kodata/tekton-addon/addons/01-clustertriggerbindings/gitlab.yaml)

Triggers created by OpenShift:

**EventListener:**

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: EventListener
metadata:
  creationTimestamp: '2024-07-08T03:05:36Z'
  generation: 1
  name: event-listener-l8fnuu
  namespace: gxjiao-proj
  resourceVersion: '53282689'
  uid: 6a2581d9-0326-4b32-b568-dd65da3c80d4
spec:
  namespaceSelector: {}
  resources: {}
  serviceAccountName: pipeline
  triggers:
    - bindings:
        - kind: ClusterTriggerBinding
          ref: gitlab-review-comment-on-mergerequest
      template:
        ref: trigger-template-build-pipeline-7ckav0
status:
  address:
    url: 'http://el-event-listener-l8fnuu.gxjiao-proj.svc.cluster.local:8080'
  conditions:
    - lastTransitionTime: '2024-07-08T03:05:36Z'
      message: Deployment does not have minimum availability.
      reason: MinimumReplicasUnavailable
      status: 'False'
      type: Available
    - lastTransitionTime: '2024-07-08T03:05:36Z'
      message: Deployment exists
      status: 'True'
      type: Deployment
    - lastTransitionTime: '2024-07-08T03:05:36Z'
      message: ReplicaSet "el-event-listener-l8fnuu-7cbff8b66c" is progressing.
      reason: ReplicaSetUpdated
      status: 'True'
      type: Progressing
    - lastTransitionTime: '2024-07-08T03:05:36Z'
      message: 'Condition Available has status: False with message: Deployment does not have minimum availability.'
      status: 'False'
      type: Ready
    - lastTransitionTime: '2024-07-08T03:05:36Z'
      message: Service exists
      status: 'True'
      type: Service
  configuration:
    generatedName: el-event-listener-l8fnuu

```

**TriggerTemplate**:

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
  creationTimestamp: '2024-07-08T03:05:36Z'
  generation: 1
  managedFields:
    - apiVersion: triggers.tekton.dev/v1beta1
      fieldsType: FieldsV1
      fieldsV1:
        'f:spec':
          .: {}
          'f:params': {}
          'f:resourcetemplates': {}
      manager: Mozilla
      operation: Update
      time: '2024-07-08T03:05:35Z'
  name: trigger-template-build-pipeline-7ckav0
  namespace: gxjiao-proj
  resourceVersion: '53282646'
  uid: 7d928052-12a1-4f8c-99a5-23cf4519d4da
spec:
  params:
    - name: mergereq-url
    - name: comment-description
    - name: comment-url
    - name: mr-owner
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        annotations: {}
        generateName: build-pipeline-
        labels:
          tekton.dev/pipeline: build-pipeline
        namespace: gxjiao-proj
      spec:
        params:
          - name: git-command
            value: echo "$(tt.params.comment-description)"
        pipelineRef:
          name: build-pipeline
        status: null
        workspaces:
          - emptyDir: {}
            name: source

```
