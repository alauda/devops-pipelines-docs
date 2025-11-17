---
created: '2025-10-24'
sourceSHA: TBD
---

# Component Implementation Strategy: Unified Component vs Dedicated Component

## Background

When building product features on top of Tekton community capabilities, we often encounter requirements for advanced features that need enhancement or extension. These requirements may stem from:

- Enterprise-level feature requirements (such as advanced permission control, audit logs, etc.)
- Product differentiation features (such as specific UI interactions, business process customization, etc.)
- Deep integration with internal systems (such as integration with enterprise LDAP, private Git systems, etc.)
- Performance or scale optimization (such as special optimizations for large-scale scenarios)

These capabilities are often not suitable for direct feedback to the community, for reasons such as:

1. Too customized, lacking universality
2. Related to enterprise internal systems
3. Involving technology-specific routes or proprietary technology
4. Implementation approach differs from community design philosophy

When we decide to develop these productized features, we face an architectural choice: should we add new features to a **unified multi-responsibility component**, or create **dedicated single-responsibility components** for each feature?

### Concept Clarification

- **Unified Component**: A comprehensive service that internally contains multiple Controllers or modules, responsible for handling multiple different domain functions. For example, a component that simultaneously handles Pipeline enhancement, Trigger extension, Result management, and other responsibilities, typically using a lazy-loading mechanism to enable relevant Controllers on demand.

- **Dedicated Component**: A single-responsibility service that focuses on solving problems in a specific domain. For example, the TriggerWrapper component that specifically handles Trigger enhancement, or the AuditLog component that specifically handles audit logging.

This document aims to provide decision-making guidance to help teams choose the most appropriate component architecture approach in different scenarios.

## Core Principles

When making implementation decisions, we should follow these core principles:

1. **Single Responsibility Principle**: The scope of component responsibilities should be clear and easy to understand and maintain
2. **Reasonable Boundaries**: Find a balance between service granularity and operational complexity
3. **Maintainability First**: Consider long-term maintenance costs, not just short-term development efficiency
4. **Independent Evolution Capability**: Features should be able to be released and upgraded independently
5. **Team Organization Alignment**: Component division should match team organizational structure

## Decision Framework

### When to Choose Unified Component Implementation

**Unified Component Implementation** refers to integrating multiple productized features into a comprehensive service, where the service internally contains multiple Controllers or modules that can simultaneously handle enhancement requirements in different domains.

**Lazy-loading Mechanism Implementation**:

A typical lazy-loading mechanism works through the following approach:

1. **CRD Detection**: At startup, check which Tekton CRDs are installed in the cluster (e.g., Pipeline, Trigger, Result)
2. **Conditional Controller Registration**: Only register and start Controllers for installed CRDs
3. **Dynamic Discovery**: Use Kubernetes Discovery API to query available resource types
4. **Graceful Skip**: If a required CRD is not found, log a message and skip that Controller without failing startup
5. **Watch and React**: Optionally watch for CRD installation/removal events and dynamically enable/disable Controllers

**Advantages of Lazy-loading Mechanism**:

1. **Automatic Adaptation**: Automatically enables corresponding enhancement features based on actually deployed Tekton components
2. **Resource Optimization**: Does not start unused Controllers, saving resources
3. **Flexible Deployment**: Users can selectively deploy Tekton components without manual configuration
4. **Error Reduction**: Avoids startup failures due to non-existent CRDs

#### Advantages

- **Simple Deployment**: Only need to deploy one service, reducing deployment configuration complexity
- **High Resource Efficiency**: Shares process space, memory, and connection pools, reducing resource consumption
- **Good Code Reuse**: Common logic (such as Kubernetes Client, logging, monitoring, etc.) only needs to be implemented once
- **Fast Initial Development**: No need to define and maintain interfaces between multiple services
- **Relatively Simple Debugging**: Related logic is within one process, making debugging and problem localization relatively easy
- **Simple Dependency Management**: All features use unified dependency versions, avoiding version conflicts
- **Transactional Support**: Multiple features can be coordinated in the same context, ensuring consistency

#### Disadvantages

- **Unclear Responsibilities**: Component takes on too many responsibilities, violating single responsibility principle
- **Code Coupling Risk**: Code for different features in the same repository can easily lead to unexpected coupling
- **Limited Scalability**: Cannot scale different features independently, can only scale as a whole
- **Release Coupling**: A change to one feature requires redeploying the entire component, affecting other features
- **High Testing Complexity**: Need to test interactions and isolation between features
- **Team Collaboration Difficulties**: When multiple teams modify the same codebase, conflicts are easy to occur (if teams expand later)
- **Failure Propagation Risk**: A bug in one feature may affect the entire component, such as memory leaks
- **High Cognitive Burden**: New members may need to understand all features of the entire component to work effectively

### When to Choose Dedicated Component Implementation

**Dedicated Component Implementation** refers to creating a single-responsibility, clearly-bounded independent service for a specific feature, focusing on solving problems in a specific domain.

#### Applicable Scenarios

1. **Feature is Mature and Stable**
   - Feature has been validated, boundaries are clear
   - Expected to exist in the product long-term
   - Worth investing additional engineering costs

   **Examples**:
   - Core features validated in production environment
   - Key features that users depend on
   - Services that need to provide SLA guarantees

2. **Need Independent Scaling Strategy**
   - Feature has unique performance characteristics (such as high concurrency, high memory, CPU intensive, etc.)
   - Need to scale up/down independently based on load
   - Resource requirements differ significantly from other features

   **Examples**:
   - High-concurrency Webhook gateway (requires many instances)
   - Machine learning inference service (requires GPU)
   - Log aggregation service (requires large amounts of memory and disk I/O)

3. **Cross-team or Cross-project Reuse**
   - Feature may be used by multiple teams or projects
   - Want to provide as platform capability
   - May be open-sourced or commercialized in the future

   **Examples**:
   - Universal Webhook gateway service
   - Pipeline template marketplace
   - Reusable audit log system

4. **Different Availability Requirements**
   - Feature availability requirements vary significantly
   - Failure of certain features should not affect other features
   - Need independent fault tolerance and recovery strategies

   **Examples**:
   - Core Pipeline execution (high availability) vs statistical analysis (can tolerate brief unavailability)
   - Real-time triggers (high availability) vs offline reports (low availability)
   - Critical audit (high availability) vs experimental features (low availability)

#### Advantages

- **Clear Responsibilities**: Each component only handles a specific functional domain, conforming to single responsibility principle
- **Independent Evolution**: Can have its own version, release cadence, and technology choices
- **Failure Isolation**: Failure of one component does not affect other components
- **Independent Scaling**: Can scale up/down independently based on respective load characteristics
- **Team Autonomy**: Different teams can develop in parallel, reducing coordination costs
- **Technical Flexibility**: Can choose the most appropriate technology stack for each feature
- **Simple Testing**: Component boundaries are clear, testing scope is well-defined
- **Good Reusability**: Single-responsibility components are easier to reuse in other scenarios
- **Low Cognitive Burden**: New members only need to understand a single component's responsibilities to start working
- **Open Source Friendly**: Easier to independently open source or contribute features to the community

#### Disadvantages

- **High Operational Complexity**: Need to deploy, monitor, and maintain multiple services
- **High Resource Consumption**: Each service requires independent Pod, memory, CPU and other resources
- **Network Overhead**: Inter-component communication requires network calls, increasing latency
- **Complex Debugging**: Problem troubleshooting needs to span multiple services, requiring comprehensive distributed tracing
- **Consistency Challenges**: Distributed system consistency issues, such as transaction coordination, state synchronization, etc.
- **Interface Management Cost**: Need to define and maintain interfaces and contracts between components
- **Deployment Coordination**: Deployment and upgrade of multiple components need coordination, increasing release complexity
- **Slower Initial Development**: Need additional work to design interfaces, handle communication, implement fault tolerance, etc.
- **Version Compatibility**: Need to maintain version compatibility matrix between components

## Decision Checklist

When making implementation decisions, you can refer to the following checklist:

### Favor Unified Component

- [ ] Project is in early stage, feature boundaries are not yet clear
- [ ] Multiple features share same technology stack (all are Kubernetes Controllers)
- [ ] Features need to frequently share state or coordinate
- [ ] Cluster resources are limited, want to reduce Pod count
- [ ] Features are in exploration stage, may be adjusted or removed at any time
- [ ] All features are maintained by the same team
- [ ] Features have no special compute resource requirements

### Favor Dedicated Component

- [ ] Feature has clear domain boundaries and responsibility definition
- [ ] Feature is mature, expected to exist long-term
- [ ] Need independent scaling strategy (such as special compute resource requirements)
- [ ] Feature may be reused by other projects or teams, or may be open-sourced
- [ ] Feature availability requirements vary significantly
- [ ] Can accept additional operational costs
- [ ] Have sufficient operational resources to support multiple services

### Risk Assessment

#### Unified Component Risks

- **High Risk Signals**:
  - Different features are maintained by different teams
  - Features are heavily coupled, difficult to test
  - Frequently one feature change affects other features

#### Dedicated Component Risks

- **High Risk Signals**:
  - Too many independent services to manage (> 10)
  - Complex dependency relationships between components
  - Lack of unified monitoring and log aggregation
  - Version compatibility management is chaotic
  - Troubleshooting often needs to span multiple components

## Best Practice Recommendations

### 1. Start with Unified Component, Split When Appropriate

- **Early Stage**: Prioritize using unified component to quickly validate feasibility of multiple features
- **Growth Stage**: Identify mature features with clear boundaries, evaluate feasibility of splitting
- **Mature Stage**: Split core features into dedicated components, keep exploratory features in unified component

**Determining When to Split**:
- Feature iteration frequency is significantly higher than other features
- Feature is managed by an independent team
- Feature has unique scaling requirements
- Feature boundaries have stabilized

### 2. Always Maintain Good Module Boundaries

Even when choosing unified component, maintain good code organization:

**Recommended Architecture: Hybrid Deployment Model**

A well-designed unified component repository should support both all-in-one deployment and independent component deployment:

```
tektoncd-enhancement/
├── cmd/
│   └── all-in-one/           # All-in-one entry point
│       └── main.go           # Imports and starts all controllers
├── pipeline-enhancer/         # Independent controller #1
│   ├── cmd/
│   │   └── main.go           # Can build standalone
│   ├── pkg/
│   │   └── controller/
│   │       └── controller.go
│   └── go.mod                # Independent go module (optional)
├── trigger-wrapper/           # Independent controller #2
│   ├── cmd/
│   │   └── main.go           # Can build standalone
│   ├── pkg/
│   │   └── controller/
│   │       └── controller.go
│   └── go.mod                # Independent go module (optional)
├── result-manager/            # Independent controller #3
│   ├── cmd/
│   │   └── main.go           # Can build standalone
│   ├── pkg/
│   │   └── controller/
│   │       └── controller.go
│   └── go.mod                # Independent go module (optional)
└── shared/                    # Shared utilities (optional)
    └── pkg/
        ├── client/
        └── utils/
```

**Avoid**:
- Mixing code for different features in one file
- Having features directly call each other's internal methods
- Sharing mutable state across controllers
- Creating circular dependencies between subdirectories

### 3. Define Clear Interface Contracts

Whether unified or dedicated components, define clear interfaces:

```go
// Even within unified component, communicate through interfaces
type PipelineEnhancer interface {
    EnhancePipeline(ctx context.Context, pipeline *v1.Pipeline) error
}

type TriggerEnhancer interface {
    EnhanceTrigger(ctx context.Context, trigger *v1.Trigger) error
}
```

This facilitates future splitting or reorganization.

## Summary

### Recommended Approach: Start Unified, Split When Necessary

**Default Choice: Unified Component**

We recommend **prioritizing the unified component pattern** as the default implementation approach for new features. This strategy offers:

- **Lower Initial Barrier**: Faster development and deployment in early stages
- **Resource Efficiency**: Reduced operational overhead and resource consumption
- **Flexibility**: Can evolve into dedicated components when needed

**When to Consider Dedicated Components**

Use the decision checklist to regularly evaluate your implementation. Consider splitting into dedicated components when:

1. **Special Requirements Emerge**: Feature shows characteristics from the "Favor Dedicated Component" checklist
2. **Risk Signals Appear**: Hit high-risk indicators in the unified component risk assessment
3. **Team Structure Changes**: Different teams need to own different features
4. **Scale Requirements Differ**: Specific features need independent scaling strategies

**Migration Path**

The recommended evolution path is:

```
Phase 1: Unified Component (Default)
   ↓
Phase 2: Regular Evaluation (Use Checklist)
   ↓
Phase 3: Gradual Migration (Split mature features when necessary)
   ↓
Phase 4: Hybrid Model (All-in-one + Dedicated)
```

**Key Principle**

> **"Start simple, evolve deliberately"** - Begin with unified component for agility, split into dedicated components only when clear benefits outweigh the added complexity.

By following this pragmatic approach, teams can balance rapid development with long-term maintainability, avoiding both premature optimization and technical debt accumulation.


