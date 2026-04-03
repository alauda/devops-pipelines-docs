---
weight: 1
status: proposed
title: Tekton Results-based Log Archival, Query API, and Retention
creation-date: "2025-12-25"
category: docs
authors:
  - "@yksun"
---


# Summary

`Tekton Results`-based solution for long-term log archival via `S3`-compatible storage (`Ceph`) with `HTTP API` access. Supports platform token validation and includes patch-based log cleanup strategy.

## Scope

- Archived logs only (not live streaming)
- Tekton Pipelines workloads only

# Motivation

## Background
Console obtains logs from live `Pods` and platform `Elasticsearch`; lacks consistent, scalable archive for historical troubleshooting.

## Problems
- `PVC`-based archival: inefficient, hard to scale, not community-recommended
- No unified solution for cost-effective, queryable log archival
- `Results` exposes `gRPC` APIs (not browser-consumable)
- Retention agent only cleans database records, orphans log files in `S3`/external storage
- No clear retention/cleanup strategy causes unbounded growth

## Target Users
Platform admins, DevOps engineers, product/backend/frontend engineers

## Goals

- Define log storage backend: `S3`-compatible storage (`Ceph`) as primary solution
- Design `HTTP`-based API for log query/retrieval (no `gRPC` requirement)
- Define retention/cleanup strategies for archived logs and Results records
- Discuss integration architecture between Results and external logging systems

## Non-Goals

- Redesigning live Pod log streaming (focus: archived logs only)
- General-purpose logging for all workloads (scope: `Tekton Pipelines` only)
- Detailed `LokiStack`/`Loki` deployment instructions

# Requirements

## Functional

- Archive `PipelineRun`/`TaskRun` logs via `Results` to `S3`-compatible object storage (`Ceph`)
- `HTTP`-based API for browser-consumable log retrieval
- Filter by namespace/`PipelineRun`/`TaskRun`/step
- Integrate with existing auth/authz so users only access permitted logs
- Retention/cleanup mechanism for both database records and archived log payloads
- Backward compatible (fall back to live Pod logs when archival disabled)

## Non-Functional

- Scale to large `PipelineRun` counts and high log volumes without degradation
- Durable storage resilient to node/cluster failures
- Acceptable latency for interactive UI usage
- `TLS` + platform-standard authentication for all communications
- Metrics/logging for monitoring health, performance, error rates
- Minimal operational complexity with clear configuration

## Out of Scope

- Logs for non-Tekton workloads or arbitrary Pods
- Replacing cluster-wide logging stack beyond Tekton needs
- Full-featured log analytics/search UI (handled by external systems)
- Provider-specific lifecycle controllers for storage backends

# Proposal

## Architecture Overview

- **Storage**: `Ceph S3` (primary solution)
- **Security**: Platform token validation (target)
- **API**: `HTTP` interface on `Tekton Results`
- **Retention**: Patch-based cleanup (database + `S3` objects)
- **Alternative**: `LokiStack` (low feasibility, no platform support committed)

## Log Storage Solution

### Recommended Approach

**Primary solution: Ceph S3 object storage**
- Platform already supports `Ceph` (low adoption cost, production-ready)
- Leverages `Results`' log management and indexing
- Proven integration with `Results` API
- **Status**: Current implementation, recommended for production

**Potential alternative: `LokiStack`-based logging** (Low Feasibility)
- Community best practice for scalable, queryable storage
- Logs forwarded via standard forwarders/sidecars
- **Blockers**:
  - Platform lacks built-in `LokiStack` offering
  - No committed plan from AIT/platform teams to offer `LokiStack` as tenant-facing service on `ACP`
  - High implementation and operational cost
- **Status**: Backup option only; not recommended for current roadmap

**Not recommended: `PVC`-based storage**
- Community discourages: poor scalability, resource inefficiency, high operational overhead
- Only for legacy/transitional fallback


## Security and Authentication

### Target Model: Platform Token Validation (Recommended)

**Flow**:
1. Business cluster reads `kube-public/global-info` `ConfigMap` to discover:
   - Platform URL
   - Cluster name (as known to platform)
2. Calls platform API to validate incoming `ACP` tokens
3. Platform performs `SubjectAccessReview`-style checks for authorization

**Benefits**:
- Authentication by platform (not business cluster's `K8s` API)
- `RBAC`-aligned via platform `SubjectAccessReview`
- Multi-cluster compatible, no `Dex` dependency in business clusters

### Current Model: `Dex`-based Validation

**Characteristics**:
- Low implementation cost (extends existing `Results` API)
- Minimal client changes

**Limitations**:
- Cannot reliably verify token validity in business clusters (post-revocation/expiration)
- Depends on `Dex` availability, not fully aligned with `K8s` `RBAC`
- Poor multi-cluster support

## Log Query Interface

`HTTP API` via `Tekton Results`, details in `Design Details` section.

## Data Retention and Cleanup Strategy

### Current State and Limitations

**Existing functionality**:
- Database retention: `Results` cleans old `Result`/`Record` entries via `defaultRetention` and `runAt` in `ConfigMap`
- **Gap**: Retention agent does NOT clean log payloads in `S3`/`LokiStack`/`PVC` → unbounded storage growth

**Operational challenges**:
- Manual ad-hoc cleanup scripts or `S3` lifecycle policies (decoupled from `Results` settings)
- No unified view of retention across database + log storage

### Community Proposal

[tektoncd/community#1158](https://github.com/tektoncd/community/pull/1158) proposes:
- Unified cleanup for database + log storage backends
- Fine-grained policies (per-namespace, per-pipeline, status-based)
- **Status**: Under review, timeline uncertain

### Implementation Strategies

#### Strategy 1: Existing Functionality Only (NOT Recommended)
- Use only current retention agent (database cleanup)
- Rely on `S3` lifecycle policies for logs
- **Limitations**: No log cleanup, database-storage inconsistency, unbounded growth
- **Use case**: Small-scale/transitional only

#### Strategy 2: Patch-based Cleanup (Recommended)

**Implementation** (~200 lines):
1. Extend retention agent and `Results API` to invoke `DeleteLog` API for `S3` objects before deleting database records
2. **Deletion Behavior (Context-aware)**:
   - **Background Retention Agent**: In-place retry strategy. If `S3` deletion fails (except 404), the agent performs an immediate retry with exponential backoff. After 5 failed attempts, the error is ignored and the database record is deleted to ensure overall cleanup progress. This prevents transient storage issues from permanently blocking database retention.
   - **User-initiated API Deletion**: Consistent retry strategy. Also performs up to 5 retries with exponential backoff if `S3` deletion fails (except 404). If retries are exhausted, it ignores the error and proceeds with database record deletion. This ensures users are not blocked by transient storage backend issues while maintaining a best-effort cleanup of log payloads.
3. **Error handling (fail-safe)**:
   - 404 (Not Found) → Treat as success, proceed to delete database record
   - Other errors (503, timeouts, permissions) → Follow the context-aware behavior defined above
   - Log detailed context (`Result ID`, error type, message)
   - **Note**: If deletion ultimately fails via retries, users can rely on [Alternative: Ceph S3 Lifecycle Policies](#alternative-ceph-s3-lifecycle-policies) as a fallback cleanup configuration.
4. Idempotent: handles re-runs without duplicate deletions

**Benefits**:
- Unified cleanup (database + S3 together)
- Low cost (~200 lines, leverages existing components)
- Quick delivery (addresses immediate need)
- Reuses existing config (no new retention syntax)

**Limitations**:
- Simple time-based policy only (no per-namespace/status-based)
- Requires patch maintenance on upstream upgrades
- S3-focused (`LokiStack`/`PVC` need additional work)

**Recommended for**: Production needing working cleanup solution short-term

**Configuration example**:

```yaml
apiVersion: operator.tekton.dev/v1alpha1
kind: TektonConfig
metadata:
  name: config
spec:
  result:
    logs_api: true
    logs_type: S3
    db_secret_name: tekton-results-postgres
    is_external_db: true
    db_host: "postgres.external.svc.cluster.local"
    options:
      configMaps:
        tekton-results-config-results-retention-policy:
          data:
            defaultRetention: "30"  # days
            runAt: "0 2 * * *"      # daily 2AM
```

#### Full Configuration Example (External DB + S3)

To connect to an external PostgreSQL database and S3-compatible storage, you need to create a Secret containing all credentials and then configure `TektonConfig`.

#### 1. Create the Secret

Make sure the DB credentials are correctly stored into a `k8s` `secret`.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: tekton-results-postgres
  namespace: tekton-pipelines
type: Opaque
stringData:
  # Database Credentials
  POSTGRES_USER: example
  POSTGRES_PASSWORD: example
```

The same as the S3 credentials

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my_s3_secret
  namespace: tekton-pipelines
type: Opaque
stringData:
  S3_BUCKET_NAME: foo
  S3_ENDPOINT: https://example.localhost.com
  S3_HOSTNAME_IMMUTABLE: "false"
  S3_REGION: region-1
  S3_ACCESS_KEY_ID: example
  S3_SECRET_ACCESS_KEY: example
  S3_MULTI_PART_SIZE: "5242880"
```


#### 2. Configure TektonConfig
Enable the results component and specify the external database details.

```yaml
apiVersion: operator.tekton.dev/v1alpha1
kind: TektonConfig
metadata:
  name: config
spec:
  profile: all
  targetNamespace: tekton-pipelines
  result:
    is_external_db: true
    db_host: "postgres.external.svc.cluster.local"
    db_port: 5432
    db_name: "tekton_results"
    db_secret_name: "tekton-results-postgres"
    secret_name: "my_s3_secret"
    logs_api: true
    logs_type: S3
```

#### Strategy 3: Community Proposal Implementation (Future)
- Wait for upstream proposal merge, adopt full implementation
- **Benefits**: Most comprehensive, no patch maintenance, advanced policies
- **Limitations**: High cost, uncertain timeline, delayed delivery
- **Use case**: Long-term planning, low current log volumes

### Alternative: Ceph S3 Lifecycle Policies

**Mechanism**: [Ceph S3 bucket lifecycle rules](https://docs.redhat.com/en/documentation/red_hat_ceph_storage/7/html/developer_guide/ceph-object-gateway-and-the-s3-api#s3-bucket-lifecycle_dev) auto-expire objects after N days

**Pros**:
- No dependency on retention agent
- Simple bucket-level config
- Reduced operational overhead

**Cons**:
- Database-storage inconsistency (DB references deleted logs)
- No fine-grained control (uniform bucket-wide expiration)
- Delayed cleanup (runs once/day)

**Use case**: Fallback when retention agent unavailable, or environments tolerating inconsistency

**Recommendation**: Strategy 2 (patch-based) for production; S3 lifecycle as defense-in-depth





# Design Details

## Log Query API Design

### Design Goals
- HTTP contract for archived logs (S3/PVC backends; LokiStack support not prioritized)
- Retrieve logs by PipelineRun/TaskRun/step using stable identifiers
- Support single-shot retrieval and streaming ("follow") for log viewers
- Compatible with existing Results data model

### HTTP Endpoints

**Direct log retrieval**:
```
GET /apis/results.tekton.dev/v1alpha2/parents/{namespace}/results/{resultID}/logs/{logID}
Authorization: Bearer <token>
Response: text/plain log stream
```

**Step-by-step lookup flow** (common UI pattern):
> **Note on Path Variables**:
> - `{namespace}`: The namespace where your PipelineRuns / TaskRuns created, e.g., `ylf-test-1`.
> - `{result.name}`: Obtained from `results[].name` in Step 1 (e.g., `ylf-test-1/results/93a5...`).
> - `{record.name}`: Obtained from `records[].name` in Step 2 (e.g., `ylf-test-1/results/.../logs/4521...`).

1. **List Results**:
   ```
   GET /apis/results.tekton.dev/v1alpha2/parents/{namespace}/results
   ```
   Response: JSON array with Result metadata
   ```json
    {
      "results": [
        {
          "name": "ylf-test-1/results/93a5c255-4c39-4a37-a465-c37f16aa839c",
          "id": "04feeb8a-db20-4462-991a-d16cb397b1f5",
          "uid": "04feeb8a-db20-4462-991a-d16cb397b1f5",
          "created_time": "2026-01-14T22:26:54.636018Z",
          "create_time": "2026-01-14T22:26:54.636018Z",
          "updated_time": "2026-01-14T22:27:03.798364Z",
          "update_time": "2026-01-14T22:27:03.798364Z",
          "annotations": {
            "object.metadata.name": "test-cvlfr",
            "tekton.dev/pipeline": "test"
          },
          "etag": "04feeb8a-db20-4462-991a-d16cb397b1f5-1768429623798364544",
          "summary": {
            "record": "ylf-test-1/results/93a5c255-4c39-4a37-a465-c37f16aa839c/records/93a5c255-4c39-4a37-a465-c37f16aa839c",
            "type": "tekton.dev/v1.PipelineRun",
            "end_time": "2026-01-14T09:07:47Z",
            "status": "SUCCESS"
          }
        }
      ]
    }
   ```

2. **Get log records for a Result**:
   ```
   GET /apis/results.tekton.dev/v1alpha2/parents/{result.name}/logs
   ```
   Response: JSON `{"records": [...]}` where each record's `name` field is the log endpoint path
   ```json
    {
      "records": [
        {
          "name": "ylf-test-1/results/2f43a117-16be-41cf-a370-a0e53dcf7eed/logs/452120f7-6b75-3a1e-83a6-6784a7d70482",
          "id": "f1dac389-b786-420b-9625-387e7a9c4919",
          "uid": "f1dac389-b786-420b-9625-387e7a9c4919",
          "data": {
            "type": "results.tekton.dev/v1alpha3.Log",
            "value": "<base64 encoded log record metadata>"
          },
          "etag": "f1dac389-b786-420b-9625-387e7a9c4919-1768429615009569835",
          "created_time": "2026-01-14T22:26:54.854361Z",
          "create_time": "2026-01-14T22:26:54.854361Z",
          "updated_time": "2026-01-14T22:26:55.009569Z",
          "update_time": "2026-01-14T22:26:55.009569Z"
        }
      ]
    }
   ```

3. **Stream log content**:
   ```
   GET /apis/results.tekton.dev/v1alpha2/parents/{record.name}
   ```
   Response: text/plain log lines for that TaskRun
   ```
    ---> Doing curl
    % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
    Dload  Upload   Total   Spent    Left  Speed
    100 26137    0 26137    0     0  63164      0 --:--:-- --:--:-- --:--:-- 63132
   ```

**Optional query parameters**: `tailLines`, `sinceSeconds`, `follow` (Results API support varies)

See [OpenAPI spec](https://github.com/tektoncd/results/blob/v0.17.2/docs/api/openapi.yaml#L246) for canonical schema.

### Sizing Guidelines

- **Storage**: `avg_log_size × runs/hour × retained_hours` (compression reduces 30-60%)
- **`S3`**: ~7TiB/month for 2,000 `PipelineRun`s/hour @ 5MiB logs
  - *Derivation*: 2,000 runs/hr × 5 MiB/run × 24 hr/day × 30 days/mo × 0.5 (compression) ÷ 1,024 ÷ 1,024 ≈ 6.87 TiB/month
- **Database**: 2-4 vCPUs, 8-16GiB RAM, IOPS scaled to run volume

### Performance Characteristics

**Impact on TaskRun/PipelineRun execution**:
- Log archival via existing logging stack (forwarders) or async `Results API` uploads
- No additional `init`/`sidecar` containers (beyond standard logging)
- `Cold-start` and execution time comparable to clusters with centralized logging

**Impact on Results components**:
- Main load: `Results API`/watcher/database (stores metadata, serves `HTTP` queries)
- Scales with completed runs and log volume
- Mitigations: Size database appropriately, horizontal scaling of API/watcher

**Retention agent impact**:
- Runs periodically (out-of-band from run execution)
- Patch-based cleanup adds lightweight `S3` deletion (scales linearly with expired records)
- Tune schedule, batch size, resource limits

**Large Log Volume Optimizations**:
- **Size Limits**: Per-`TaskRun` log size limits and truncation policies to prevent storage exhaustion and excessive query latency pressure (Implementation ~200 lines).

### Performance SLOs

Initial targets for production clusters (tune based on capacity):

| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| Log retrieval p95 (archived) | < 2s | > 5s |
| Log retrieval p99 (archived) | < 5s | > 10s |
| `Results API` availability (monthly) | ≥ 99.9% | < 99% |
| Log archival success rate | ≥ 98% | < 95% |
| `Results` DB CPU (steady state) | < 70% | > 85% for 10min |
| `Results` DB storage utilization | < 80% | > 90% |

## Log Size Limit and Truncation

To prevent unbounded storage growth and ensure stable query performance, a size-based truncation policy is implemented during the log archival process.

**Configuration**:
Users can optionally configure the maximum log size per `TaskRun` via the `max-log-size` key in the `Results` configuration `ConfigMap` `tekton-results-api-config`. 

**Note**: This is a **custom enhancement** (patch-based) and is not currently available in upstream Tekton Results.

**Example**:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: tekton-results-api-config
  namespace: tekton-pipelines
data:
  max-log-size: "5242880"  # Size in bytes (e.g., 5 MiB)
```

This allows fine-tuning storage usage based on specific cluster workloads.

**Behavior**:
- **Truncation Strategy**: When a `TaskRun` log exceeds the configured limit, the system will preserve the **tail** (end) of the log and discard the head (beginning). This ensures that critical error messages and completion status at the end of the execution are retained for troubleshooting.
- **Default**: To maintain consistency with community behavior, no limit is applied by default. Protection is only activated when `max-log-size` is explicitly configured.
- **Implementation**:
    - The `Watcher` performs pre-truncation before sending logs to save bandwidth.
    - The `Results API` enforces the limit during ingestion to protect storage.

**Scope**: Applied at the `TaskRun` archival level during the streaming process to `S3` backends.

**Expected capacity**: 50,000+ completed `PipelineRun`s/day with avg 5MiB logs (when sized per guidelines)

### Risks and Mitigations

**Security and access control**:
- Risk: Incorrect token validation grants unauthorized log access
- Mitigations:
  - `Dex` mode: Short-lived tokens (≤60min), validate signature/issuer/audience/expiration on every request
  - Hard denial on validation failure (no unauthenticated fallback)
  - `SubjectAccessReview` against `PipelineRun`/`TaskRun` where possible
  - No authorization caching beyond token lifetime

**Data consistency and durability**:
- Risk: Transient backend failures cause missing/partial logs
- Mitigations:
  - At-least-once delivery in log forwarders
  - Metrics/alerts for forwarding/ingestion failures
  - UI clearly distinguishes "logs missing"/"delayed" from "no logs produced"

**Resource and scalability**:
- Risk: Results/log backends become bottlenecks under high volume
- Mitigations:
  - Conservative default retention in `TektonConfig`
  - Document sizing guidance
  - Monitor latency/errors/storage utilization with alerts

**User experience**:
- Risk: Archived log latency higher/variable than live Pods; permission errors unclear
- Mitigations:
  - Clear `UI` copy for loading/missing logs/access-denied states
  - `UX`/product team review of error surfaces
  - Gather early adopter feedback before broad rollout



### Drawbacks

Reasons NOT to implement this TEP:

- **Increased infrastructure overhead**: `Results` (`DB`/`API`/watcher) + logging/object storage more complex than live `Pod` logs or simple `PVC`s
- **Stronger `Results` dependency**: Ties `UI`/integrations to `Results` availability and schema
- **Inconsistent capabilities**: Actual query features may vary if alternative backends (e.g., `LokiStack`) are adopted in the future
- **Eventual consistency**: Archived logs available with delay; rare failures cause missing logs (vs immediate `Pod` log access)

### Alternatives (Rejected)

**Continue PVC-based storage**:
- Simple, no external systems
- Rejected: Poor scaling, expensive block storage, operationally cumbersome for long-term retention

**External logging stack only (no Results)**:
- Forward logs to external logging system (e.g., `LokiStack`), treat as generic app logs
- Rejected: 
  - `UI` lacks stable contract for `PipelineRun`/`TaskRun`/step correlation
  - No platform commitment to provide `LokiStack` as consumable service
  - Must reimplement per-backend logic

**Kubernetes Pod log APIs only**:
- Build on `/log` endpoints without archival
- Rejected: Logs unavailable after `Pod` deletion; can't support long-term troubleshooting/compliance

### Test Plan

**Unit**:
- Config parsing (`S3`/`PVC` backends; `LokiStack` support deferred)
- Retention fields validation (`defaultRetention`, `runAt` via `Options.ConfigMaps`)
- Retention agent logic (mock `DB` queries, `S3` deletions)

**Integration**:
- Deploy `Results` with mocked `Ceph` endpoint, verify `HTTP` log read/write
- Retention agent: verify `S3` payloads deleted with database records

**E2E**:
- Run Pipelines, verify `HTTP API` log access
- Retention: short window (1h), confirm database + `S3` cleanup
- Error handling: simulate `S3` failures, verify exponential backoff retry (up to 5 times) and eventual database record deletion after 5 failures to prevent blocking progress
- Platform token auth and `RBAC`

**Scale and resilience**:
- 2,000+ `PipelineRun`s/hour @ 5MiB logs, verify `SLO`s and no data loss
- Long-running queries (multi-hour ranges), verify timeouts/streaming
- Horizontal scaling (multiple API/watcher replicas, sharded watcher)

**Failure modes**:
- Degrade log backend (`S3`), verify retries/`UI` errors/metrics
- `Database` failover, verify no log loss and idempotent reconciliation
- Network partitions (business ↔ control-plane), verify clear auth failures

**Concurrency and longevity**:
- 100+ concurrent `UI` sessions, verify `p95` latency and resource usage
- Multi-day workload, validate retention/growth matches sizing

**Telemetry**:
- Monitor upload/read paths under realistic concurrency
- `Prometheus` metrics: `grpc_server_handled_total{grpc_method="CreateResult", grpc_code="OK"}` for archival throughput
- Aggregate non-OK codes for failure rates

### Operational Ownership

Production `ACP` deployments: Platform/`SRE` team owns day-2 ops (on-call, capacity planning, upgrades) for `Results` stack (`API`/watcher/`DB`/log backends). Application teams own Pipeline definitions and retention policies.



# References

- [`TEP`-0021: `Tekton Results` API](https://github.com/tektoncd/community/blob/main/teps/0021-results-api.md)
- [`Tekton Results` Documentation](https://github.com/tektoncd/results/blob/main/docs/README.md)
- [`Tekton Results` OpenAPI](https://github.com/tektoncd/results/blob/v0.17.2/docs/api/openapi.yaml)
- [Retention Enhancement Proposal](https://github.com/tektoncd/community/pull/1158)

# Future Considerations

## `LokiStack` Integration (Low Priority)

**Current status**: No committed plan from AIT/platform teams to offer `LokiStack` as tenant-facing service on `ACP`.

**Potential future work** (only if platform support becomes available):
- Evaluate `LokiStack` deployment models and operational requirements
- Design integration between `Results` and `LokiStack` API
- Implement log forwarder configuration and lifecycle management

**Recommendation**: Continue with `Ceph S3` as primary solution; revisit `LokiStack` only if platform strategy changes.

## Enhanced Log Collection
- Finalizer-based protection against early `Pod` deletion to mitigate race conditions during archival (~500 lines).
- Strategy to achieve 99.99% archival success rate: current post-`TaskRun` archival trigger is highly susceptible to early `Pod` `GC`; exploring interim buffer or real-time streaming alternatives.

## Large Log Volume
- Semaphore-based `S3` upload concurrency limiter.
- Priority-based archival scheduling.

## Query Enhancements
`tailLines`, `sinceSeconds`, backend-specific filters

## Operational Runbooks
Separate deliverables: `LokiStack` deployment, `DB` backup/restore, disaster recovery, troubleshooting guides


