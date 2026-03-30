---
title: Tekton Metrics Collection and Visualization
authors:
  - zcyu@alauda.io
creation-date: 2025-12-29T00:00:00.000Z
last-updated: 2025-12-29T00:00:00.000Z
status: proposed
---

# TEP-0008: Tekton Metrics: Collection and Visualization

## Summary

This document proposes a metrics collection and visualization approach for `Tekton`. It:

- Surveys `Tekton` built-in metrics and clarifies their semantics.
- Defines a `Prometheus`-compatible collection approach that works with both `Prometheus` and `VictoriaMetrics` on `AIT`.
- Designs a baseline set of dashboards (graphs) that can be built from existing `Tekton` metrics.
- Identifies gaps and proposes optional extensions (new metrics and/or additional labels) as needed.
- Discusses a configuration-driven mechanism to extend metrics with minimal code changes.

## Motivation

`Pipeline` observability is a core requirement for `DevOps` platforms: teams need to understand execution volume, success/failure rates, latency distributions, and resource bottlenecks. `Tekton` already exposes a useful metrics surface, but:

- The platform needs a standardized way to scrape, store, and render dashboards.
- Some product requirements cannot be fulfilled using built-in `Tekton` metrics alone (e.g., “how many `Pipelines` have ever been executed?” or vulnerability counts from a scanner).

This document aims to provide a consistent, low-friction plan aligned with `AIT`'s monitoring stack.

### Goals

1. Survey `Tekton` built-in metrics and make their meaning explicit.
2. Design a metrics collection approach on `AIT`.
3. Design a dashboard (graph) plan for common `DevOps` use-cases.
4. Provide a generic mechanism so projects can add metrics via configuration.

### Non-goals

- Replacing `AIT`'s monitoring components (`Prometheus`/`VictoriaMetrics`) with a bespoke stack.
- Building a `Kibana`-first metrics UI as the primary path (it can be integrated later).
- Redesigning `Tekton`'s upstream metrics model (this proposal prefers additive extensions).

## Background: AIT monitoring landscape

Reference: [Monitoring Component Selection Guide](https://docs-dev.alauda.cn/container_platform/main/observability/monitor/architecture/component_selection_suggestion.html).

`AIT` provides two monitoring components:

- **`VictoriaMetrics`**: for high availability and multi-cluster monitoring scenarios.
- **`Prometheus`**: for single-cluster monitoring scenarios, especially smaller scale.

Both require `Prometheus`-compatible targets:

- **`Prometheus`**: scrapes `/metrics` via HTTP GET; target must expose `Prometheus`/`OpenMetrics` text format.
- **`VictoriaMetrics`**: `vmagent` can replace `Prometheus` as the “scraper”, scraping `Prometheus`-compatible targets (the same `/metrics` endpoints); scrape configuration is largely Prometheus-compatible.

For visualization, `AIT` recommends:

- Using the platform's [built-in Dashboard](https://docs-dev.alauda.cn/container_platform/main/observability/monitor/functions/manage_dashboard.html) capability for charts.
- Optionally [deploying Grafana via an S2 solution](https://confluence.alauda.cn/display/AL/Deploying+Grafana+-+Solution+S2).

`AIT` provides a generic integration mechanism: products only need to ship CRs for [collection](https://confluence.alauda.cn/pages/viewpage.action?pageId=184355675) and [dashboard rendering](https://confluence.alauda.cn/pages/viewpage.action?pageId=206080421) together with the product release.

### Why start with Prometheus-compatible metrics

`Prometheus` remains the most common metrics solution with a strong ecosystem, and `AIT` already supports the `Prometheus` family (including `VictoriaMetrics` scraping). Therefore, we prioritize `Prometheus`-compatible metrics as the foundation.

`AIT` can also forward data to external systems (e.g., `ES`, `Kafka`). In principle, once we integrate with `AIT`'s mechanism, downstream integrations can reuse it.

### Notes on `Elasticsearch` + `Kibana`

`Elasticsearch` + `Kibana`'s main advantage is that logs/metrics/traces can be stored in `ES` and analyzed together in `Kibana`.

However:

- `AIT`'s current dashboard system is built around the `Prometheus` query model; an `ES`-based approach typically requires projects to deploy and operate `Kibana` themselves, with weaker platform support.
- If you already expose `Prometheus` metrics, you can often keep the collection side mostly unchanged and forward data to `ES` using tools such as `Metricbeat` + `Prometheus` `remote_write`. The main migration cost is dashboard adaptation (`PromQL` → `Kibana`/`ES` query model).

## Metrics

### Metric types

- **Counter**: monotonically increasing count; suited for “number of events” (e.g., completed runs). Usually used with `rate()` / `increase()` in `Prometheus`.
- **Gauge / LastValue**: point-in-time value (the latest observed value); suited for “currently running” counts or instantaneous state.
- **Histogram**: distribution statistics (`bucket`, `sum`, `count`); suited for latency/duration where percentiles are needed.

> **Histogram vs LastValue (Gauge)**
>
> `Tekton`'s duration metrics can be configured to expose either Histogram or LastValue depending on:
> - `metrics.taskrun.duration-type`
> - `metrics.pipelinerun.duration-type`

> **How histograms appear in `Prometheus`**
>
> A single histogram expands into three series families:
> - `*_bucket`: cumulative count for each bucket boundary
> - `*_sum`: sum of all observed values
> - `*_count`: number of samples
>
> In this document, histogram metrics annotated with `[bucket, sum, count]` mean all three are exposed. `Prometheus` can compute averages and percentiles (e.g., `histogram_quantile()`).
>
> Default buckets: `10, 30, 60, 300, 900, 1800, 3600, 5400, 10800, 21600, 43200, 86400`

### Tekton Pipelines default metrics and recording method

Reference: [Tekton Pipelines metrics documentation](https://tekton.dev/docs/pipelines/metrics/).

> Note: depending on deployment, metric names may be prefixed (e.g., `tekton_pipelines_controller_`). The table below follows the names used in the original survey.

| Metric                                                      | Purpose                                                                       | Recording method                                                      | Type                          | Labels/Tags                                                                                                                                                                                                 |
|-------------------------------------------------------------|-------------------------------------------------------------------------------|-----------------------------------------------------------------------|-------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `pipelinerun_duration_seconds_[bucket, sum, count]`         | `PipelineRun` execution duration                                              | Event-driven (recorded when a `PipelineRun` reaches a terminal state) | Histogram / LastValue (Gauge) | `pipeline=<pipeline_name>`<br>`pipelinerun=<pipelinerun_name>`<br>`status=<status>`<br>`namespace=<pipelinerun-namespace>`                                                                                  |
| `pipelinerun_taskrun_duration_seconds_[bucket, sum, count]` | `TaskRun` duration inside a `PipelineRun`                                     | Event-driven (recorded when a `TaskRun` reaches a terminal state)     | Histogram / LastValue (Gauge) | `pipeline=<pipeline_name>`<br>`pipelinerun=<pipelinerun_name>`<br>`status=<status>`<br>`task=<task_name>`<br>`taskrun=<taskrun_name>`<br>`namespace=<pipelineruns-taskruns-namespace>`<br>`reason=<reason>` |
| `pipelinerun_total`                                         | Total number of `PipelineRuns` that have **completed since controller start** | Event-driven (increment when `PipelineRun` reaches a terminal state)  | Counter                       | `status=<status>`                                                                                                                                                                                           |
| `running_pipelineruns`                                      | Number of currently running `PipelineRuns`                                    | Periodic (default ~30s, counted from informer cache)                  | Gauge                         | (depends on `metrics.running-pipelinerun.level`)                                                                                                                                                            |
| `taskrun_duration_seconds_[bucket, sum, count]`             | `TaskRun` execution duration                                                  | Event-driven (recorded when a `TaskRun` reaches a terminal state)     | Histogram / LastValue (Gauge) | `status=<status>`<br>`task=<task_name>`<br>`taskrun=<taskrun_name>`<br>`namespace=<pipelineruns-taskruns-namespace>`<br>`reason=<reason>`                                                                   |
| `taskrun_total`                                             | Total number of `TaskRuns` that have **completed since controller start**     | Event-driven (increment when `TaskRun` reaches a terminal state)      | Counter                       | `status=<status>`                                                                                                                                                                                           |
| `running_taskruns`                                          | Number of currently running `TaskRuns`                                        | Periodic (default ~30s, counted from informer cache)                  | Gauge                         | (depends on configuration)                                                                                                                                                                                  |
| `running_taskruns_throttled_by_quota`                       | Running `TaskRuns` throttled by `ResourceQuota`                               | Periodic (default ~30s, counted from informer cache)                  | Gauge                         | `namespace=<pipelinerun-namespace>`                                                                                                                                                                         |
| `running_taskruns_throttled_by_node`                        | Running `TaskRuns` throttled by node resource constraints                     | Periodic (default ~30s, counted from informer cache)                  | Gauge                         | `namespace=<pipelinerun-namespace>`                                                                                                                                                                         |
| `client_latency_[bucket, sum, count]`                       | `Kubernetes` API request latency                                              | Event-driven (recorded per API request)                               | Histogram                     | (standard client labels)                                                                                                                                                                                    |

### Tekton Triggers controller metrics {#tekton-triggers-controller-metrics}

Reference: [Tekton Triggers metrics documentation](https://tekton.dev/docs/triggers/metrics/).

| Name                                     | Type  | Description                        |
|------------------------------------------|-------|------------------------------------|
| `controller_clusterinterceptor_count`    | Gauge | Number of `ClusterInterceptors`    |
| `controller_eventlistener_count`         | Gauge | Number of `EventListeners`         |
| `controller_clustertriggerbinding_count` | Gauge | Number of `ClusterTriggerBindings` |
| `controller_triggerbinding_count`        | Gauge | Number of `TriggerBindings`        |
| `controller_triggertemplate_count`       | Gauge | Number of `TriggerTemplates`       |

> We can consider adding count metrics for new resources such as `ScheduledTrigger` in the future.
> Additional metrics for scenarios such as approvals can be added on demand.

### Semantics of `pipelinerun_total` and `taskrun_total`

`pipelinerun_total` and `taskrun_total` are easy to misunderstand:

1. They are **not** the total number of `PipelineRun`/`TaskRun` objects currently in the cluster.
   They represent the number of `PipelineRuns`/`TaskRuns` that have **completed (reached terminal state) since the controller started**.
2. They are computed during reconciliation and increment only when `status.conditions[?type=="Succeeded"]` changes into a terminal state.
3. As Counters, they only increase.
4. They reset to zero when the `Tekton Pipelines` controller restarts. In `PromQL`, use `increase()`/`rate()`: `Prometheus` can detect counter resets and still compute the correct windowed increment.

## Default metrics configuration

Reference:
- `Pipelines`: [config-observability.yaml](https://github.com/tektoncd/pipeline/blob/release-v1.7.x/config/config-observability.yaml) (`Tekton Pipelines`)
- `Triggers`: [config-observability.yaml](https://github.com/tektoncd/triggers/blob/release-v0.32.x/config/config-observability.yaml) (`Tekton Triggers`)

| `ConfigMap` key                             | Value         | Description                                                                                                                                  |
|---------------------------------------------|---------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| `metrics.taskrun.level`                     | `taskrun`     | Metrics level is `TaskRun`                                                                                                                   |
| `metrics.taskrun.level`                     | `task`        | Metrics level is `Task`; `taskrun` label is not present                                                                                      |
| `metrics.taskrun.level`                     | `namespace`   | Metrics level is Namespace; `task` and `taskrun` labels are not present                                                                      |
| `metrics.pipelinerun.level`                 | `pipelinerun` | Metrics level is `PipelineRun`                                                                                                               |
| `metrics.pipelinerun.level`                 | `pipeline`    | Metrics level is `Pipeline`; `pipelinerun` label is not present                                                                              |
| `metrics.pipelinerun.level`                 | `namespace`   | Metrics level is Namespace; `pipeline` and `pipelinerun` labels are not present                                                              |
| `metrics.running-pipelinerun.level`         | `pipelinerun` | Level of running `PipelineRun` metrics is `PipelineRun`                                                                                      |
| `metrics.running-pipelinerun.level`         | `pipeline`    | Level of running `PipelineRun` metrics is `Pipeline`; `pipelinerun` label is not present                                                     |
| `metrics.running-pipelinerun.level`         | `namespace`   | Level of running `PipelineRun` metrics is Namespace; `pipeline` and `pipelinerun` labels are not present                                     |
| `metrics.running-pipelinerun.level`         | ``            | Cluster-level; `namespace`, `pipeline`, `pipelinerun` labels are not present                                                                 |
| `metrics.taskrun.duration-type`             | `histogram`   | `tekton_pipelines_controller_pipelinerun_taskrun_duration_seconds` and `tekton_pipelines_controller_taskrun_duration_seconds` are histograms |
| `metrics.taskrun.duration-type`             | `lastvalue`   | The above metrics are gauges / lastvalue                                                                                                     |
| `metrics.pipelinerun.duration-type`         | `histogram`   | `tekton_pipelines_controller_pipelinerun_duration_seconds` is a histogram                                                                    |
| `metrics.pipelinerun.duration-type`         | `lastvalue`   | `tekton_pipelines_controller_pipelinerun_duration_seconds` is a gauge / lastvalue                                                            |
| `metrics.count.enable-reason`               | `false`       | Whether to include the `reason` label on count metrics                                                                                       |
| `metrics.taskrun.throttle.enable-namespace` | `false`       | Whether to include `namespace` on `tekton_pipelines_controller_running_taskruns_throttled_by_quota`                                          |

### Why these knobs exist

These configuration knobs primarily exist to control metrics volume by tuning granularity and cardinality.

Issue reference: [Too much tekton metrics which makes our monitoring system doesn't work well](https://github.com/tektoncd/pipeline/issues/2842).

Common sources of high metrics volume:

1. **Histogram metrics**: each bucket produces a time series
   <details>
     <summary>Example: histogram series expansion</summary>

     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="10"} 0
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="30"} 0
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="60"} 0
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="300"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="900"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="1800"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="3600"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="5400"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="10800"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="21600"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="43200"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="86400"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg",le="+Inf"} 1
     tekton_taskrun_duration_seconds_sum{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg"} 75
     tekton_taskrun_duration_seconds_count{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="10"} 0
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="30"} 0
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="60"} 0
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="300"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="900"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="1800"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="3600"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="5400"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="10800"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="21600"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="43200"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="86400"} 1
     tekton_taskrun_duration_seconds_bucket{namespace="2213a7c1-a282",status="success",task="anonymous",taskrun="perf-br-k-1-tw4d4",le="+Inf"} 1

   </details>

2. **High-cardinality labels**: volume grows with the number of label combinations. For example, if `taskrun_duration_seconds` includes the `taskrun` label, every `TaskRun` creates a distinct series.
   <details>
     <summary>Example: duration metric with `taskrun` label</summary>

     tekton_taskrun_duration_seconds{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg"} 101
     tekton_taskrun_duration_seconds{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-dwjha"} 112
     tekton_taskrun_duration_seconds{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-vdsva"} 134
     tekton_taskrun_duration_seconds{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fgsfe"} 123
     tekton_taskrun_duration_seconds{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-fwmbg"} 241
     tekton_taskrun_duration_seconds{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-czscw"} 334
     tekton_taskrun_duration_seconds{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-eq222"} 133
     tekton_taskrun_duration_seconds{namespace="2213a7c1-a282",status="failed",task="anonymous",taskrun="perf-br-test-10-czsca"} 132

   </details>

Example trade-off:

- If `metrics.pipelinerun.level=namespace` and `metrics.pipelinerun.duration-type=lastvalue`, the time series volume is low, but the chart shows “latest run duration” for the namespace and will jump up and down, which is not a stable percentile view.
- The defaults (`metrics.pipelinerun.level=pipeline` and `metrics.pipelinerun.duration-type=histogram`) are a reasonable compromise for typical environments: when the number of `Pipelines` is not huge, you can query pipeline-level percentiles (P90/P95) to observe tail latency.

## Dashboard (Graph) design

This section describes a set of dashboards that can be built primarily from `Tekton`'s default metrics (with default or lightly tuned configuration).

### Common graphs

| Graph                                                                          | Can be built from `Tekton` default metrics? | Notes                                                                                                                                                                                |
|--------------------------------------------------------------------------------|--------------------------------------------:|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `PipelineRun` completion trend (windowed, grouped by success/failed/cancelled) |                                         Yes | Use `pipelinerun_total` aggregated by `status` with `increase()` / `rate()` to count completions in the window.                                                                      |
| `PipelineRun` executions (windowed total)                                      |                                         Yes | Use `pipelinerun_total` with `increase()` / `rate()`; include cancelled if desired.                                                                                                  |
| `PipelineRun` success rate (success ÷ total completions, windowed)             |                                         Yes | `sum(increase(...{status="success"})) / sum(increase(...))`                                                                                                                          |
| `PipelineRun` failure rate (failed ÷ total completions, windowed)              |                                         Yes | `sum(increase(...{status="failed"})) / sum(increase(...))`                                                                                                                           |
| Top N most frequently built `Pipelines`                                        |                                         Yes | With `metrics.pipelinerun.duration-type=histogram` and `metrics.pipelinerun.level=pipeline`, use `pipelinerun_duration_seconds_count` aggregated by `pipeline` and sort with `topk`. |
| `PipelineRun` average / P90 / P95 (windowed; by pipeline or by namespace)      |                                         Yes | Requires histogram duration; pipeline grouping needs `metrics.pipelinerun.level=pipeline`; namespace grouping needs `metrics.pipelinerun.level=namespace`.                           |
| Number of running `PipelineRuns` (global or by namespace)                      |                                         Yes | Namespace grouping requires `metrics.running-pipelinerun.level=namespace` (or `pipeline` / `pipelinerun`).                                                                           |
| `TaskRun` completion trend (success/failed)                                    |                                         Yes | Use `taskrun_total` aggregated by `status` with `increase()` / `rate()`.                                                                                                             |
| `TaskRun` average / P90 / P95 (by namespace or by task)                        |                                         Yes | Requires histogram duration; task grouping needs `metrics.taskrun.level=task`; namespace grouping needs `metrics.taskrun.level=namespace`.                                           |
| (Optional) Top N failure reasons                                               |                                         Yes | Enable `metrics.count.enable-reason=true`, then aggregate by `reason`.                                                                                                               |
| (Optional) Resource pressure: running `TaskRuns` throttled by quota/node       |                                         Yes | Use `running_taskruns_throttled_by_quota` / `running_taskruns_throttled_by_node`.                                                                                                    |
| (Optional) Controller `Kubernetes` API latency (client_latency histogram)      |                                         Yes | Use histogram to compute avg / P90 / P95.                                                                                                                                            |

### Customize graphs {#customize-graphs}

| Graph                                                                                   | Can be built from `Tekton` default metrics? | Notes                                                                                                                     |
|-----------------------------------------------------------------------------------------|--------------------------------------------:|---------------------------------------------------------------------------------------------------------------------------|
| Number of `Pipelines`                                                                   |                                          No | `Pipeline` object count is not exposed; needs `Kubernetes` API or a custom exporter/metric.                               |
| Number of `PipelineRuns`                                                                |                                     Partial | `pipelinerun_total` only counts completions since controller start; windowed completions can be derived via `increase()`. |
| Ratio of `Pipelines` that have execution history (executed pipelines ÷ total pipelines) |                                          No | Requires both total pipelines and per-pipeline execution history; built-in metrics are insufficient.                      |
| Percentage of `Pipelines` with execution history                                        |                                          No | Same as above.                                                                                                            |
| `PipelineRuns` executed in past time periods                                            |                                         Yes | Use `pipelinerun_total` with `increase()`, or `pipelinerun_duration_seconds_count`.                                       |
| `PipelineRun` status breakdown (success/failed/etc.)                                    |                                         Yes | Use `pipelinerun_total` aggregated by `status`.                                                                           |
| Top N by duration for `Pipelines` and `Tasks`                                           |                                         Yes | Enable histogram durations and group by `pipeline` / `task`, compute avg or P90/P95, then sort.                           |

#### Metrics to add (gaps) {#metrics-to-add-gaps}

| Metric                      | Type    | Tags                           | Description                                                                                                                                 |
|-----------------------------|---------|--------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `pipeline_count`            | Gauge   | `namespace`                    | Count `Pipeline` objects from informer cache.                                                                                               |
| `pipelinerun_count`         | Gauge   | `namespace`, optional `status` | Count `PipelineRun` objects from informer cache; include `status` if needed.                                                                |
| `pipeline_executions_total` | Counter | `namespace`, `pipeline`        | If a pipeline has ever executed, the counter > 0 can be treated as “executed”; combine with `pipeline_count` to compute the executed ratio. |

To reduce upgrade/migration cost, extended metrics are recommended to live in a separate “tekton enhancement” component, minimizing direct modifications to upstream `Tekton` code.

#### Grouping by environment type (namespace labels)

Grouping by environment type (e.g., namespace labels) requires namespace label data in `Prometheus`. `Tekton` metrics typically include only the namespace name, not arbitrary labels.

A common approach is to use `kube-state-metrics` to expose `kube_namespace_labels`, then join in `PromQL`.

Therefore, to enable grouping by environment type, `Tekton` metrics should include a `namespace` label so that `PromQL` joins can be applied.

### Extended graph scenarios {#extended-graph-scenarios}

The graphs in the examples below are mainly to discuss scenarios we may encounter later and possible implementation approaches; they can be implemented later as needed.

There are three main cases:

1. Existing metrics are sufficient
2. New metrics are required
3. Additional tags are needed for existing metrics

When we later evaluate how to implement graphs, we can use the following criteria:

- If a graph requires new metrics:
  - If it is a general metric with product value, implement it in `tektoncd-enhancement`.
  - If it is a project-specific custom metric:
    - If it can be implemented using only `CR` fields in the cluster, provide an S1 solution using `AIT`'s [`kube-state-metrics` configuration](#community-approach-kube-state-metrics-custom-resource-state-metrics).
    - If the custom metric is provided by the customer, guide the customer to expose a metrics endpoint and configure a [`ServiceMonitor` `CR`](https://confluence.alauda.cn/pages/viewpage.action?pageId=184355675) to scrape the metrics endpoint of the service deployed in the cluster.
- If a graph requires new tags:
  - Use the configuration in [configurable additional labels](#tekton-enhancement-approach-optional-configurable-additional-labels) to implement it.

> How to decide whether to add a new metric or add a new tag? It mainly depends on data volume; compare [`Trivy` vulnerability counts](#trivy-vulnerability-counts-high--medium--low) and [Failure rate by `Task` type](#failure-rate-by-task-type).

> Alternative: provide a general mechanism in tektoncd-enhancement where users only need to label or annotate `Task`, `Pipeline`, and other resources with specified labels or annotations,
> and tektoncd-enhancement will collect data and generate metrics based on those definitions.
> This way, users neither need to manually modify `kube-state-metrics` configuration nor implement metrics themselves; they can add metrics by following the conventions.
> The specific mechanism and conventions still need detailed design and can be implemented later as needed.

#### Trivy scan success rate

No new metrics are required; this can be implemented via existing metrics and dashboard configuration:

- Set `metrics.taskrun.level=task`
- Set `metrics.taskrun.duration-type=histogram`
- Windowed success rate (example):

  `taskrun_duration_seconds_count{task="trivy",status="success"} / taskrun_duration_seconds_count{task="trivy"}`

> For histogram metrics, `*_count` is the cumulative sample count, which is equivalent to “completed `TaskRun` count” in this scenario.
> `taskrun_total` cannot be used here because it does not include the `task` label, so it cannot be filtered by `Task`.

#### Trivy vulnerability counts (High / Medium / Low) {#trivy-vulnerability-counts-high--medium--low}

This requires new metrics; `Tekton` built-in metrics cannot read vulnerability information from `TaskRun` results.

- Metric name: `trivy_vulnerabilities_total`
- Type: Counter (accumulate vulnerability counts per scan)
- Tags:
  - `severity` (`high` / `medium` / `low`)
  - `task` (fixed to `trivy`, or `scanner="trivy"`)
  - `namespace`
- Recording timing:
  - After `TaskRun` completion, parse vulnerabilities from results
  - Record increments per severity

`PromQL` example (high severity trend):

`sum(increase(trivy_vulnerabilities_total{severity="high"}[1h]))`

#### Failure rate by Task type {#failure-rate-by-task-type}

Goal: compute failure rate grouped by `Task` labels (e.g., `task.tekton.dev/type`).

This requires **adding a label to an existing metric**: `Tekton` default metrics cannot read `Task` labels today. Because we need both the existing `status` label and a new `task_type` label, reusing existing metrics helps reduce storage overhead.

- Add label: extend `taskrun_total` with `task_type` (read from `Task` labels)
- Type: Counter
- `Task` type resolution:
  - If `TaskRun.spec.taskRef.name` is set: lookup the `Task` from `Task` informer/lister and read its labels; if missing, default to `task_type="unknown"`.
  - If the `TaskRun` uses an inline `taskSpec`: `Task` labels are unavailable, default to `task_type="unknown"`.

`PromQL` (failure rate by type, 1h window):

`sum by (task_type) (increase(taskrun_total{status="failed"}[1h])) / sum by (task_type) (increase(taskrun_total[1h]))`

## A flexible, configuration-driven metrics mechanism

We want a flexible mechanism to implement metrics via configuration.

In `Tekton`, many metrics are derived from `CR` `spec` / `status`. This is a generic pattern applicable beyond `Tekton` as well.

### Community approach: `kube-state-metrics` `Custom Resource State Metrics` {#community-approach-kube-state-metrics-custom-resource-state-metrics}

`kube-state-metrics` provides [`Custom Resource State Metrics`](https://github.com/kubernetes/kube-state-metrics/blob/main/docs/metrics/extend/customresourcestate-metrics.md), which allows defining metrics from `CR` fields via configuration.

High-level steps:

1. Write custom metric rules (`CustomResourceStateMetrics`)
2. Grant `kube-state-metrics` read access to the target `CRs`
3. Mount the rules file into `kube-state-metrics`

Example config:

```yaml
kind: CustomResourceStateMetrics
spec:
  resources:
    - groupVersionKind:
        group: myteam.io
        kind: "Foo"
        version: "v1"
      metrics:
        - name: "uptime"
          help: "Foo uptime"
          each:
            type: Gauge
            gauge:
              path: [status, uptime]
```

Produces the metric:

```
kube_customresource_uptime{customresource_group="myteam.io", customresource_kind="Foo", customresource_version="v1"} 43.21
```

However, `kube-state-metrics` custom `CR` metrics are inherently "one sample per object", so the source side cannot aggregate into a single total. To control data volume, typically use these approaches:

- Aggregate with recording rules in `Prometheus`, then drop the raw metrics (most effective)
    - Example: count(kube_customresource_tektoncd_customization_pipeline_count)
- Reduce label cardinality (drop labels like status / pipeline), keep only necessary dimensions

`AIT` uses `Prometheus Operator`, so you can implement this with `PrometheusRule`:

```yaml
apiVersion: monitoring.coreos.com/v1                                                                                                                                                          
kind: PrometheusRule                                                                                                                                                                          
metadata:                                                                                                                                                                                     
  name: tekton-custom-rules                                                                                                                                                                   
  namespace: <prometheus-namespace>                                                                                                                                                           
spec:                                                                                                                                                                                         
  groups:                                                                                                                                                                                     
    - name: tekton-custom                                                                                                                                                                     
      rules:                                                                                                                                                                                  
        - record: tektoncd_customization_pipeline_total                                                                                                                                       
          expr: count(kube_customresource_tektoncd_customization_pipeline_count)                                                                                                              
        - record: tektoncd_customization_pipeline_total_by_namespace                                                                                                                          
          expr: count by (namespace) (kube_customresource_tektoncd_customization_pipeline_count)  
```

#### Platform support level (AIT)

`AIT` has used this mechanism to provide an S2 solution for custom metrics: [How to expose VerticalPodAutoscaler metrics](https://github.com/alauda/knowledge/blob/main/docs/en/solutions/How_to_expose_VerticalPodAutoscaler_metrics.md).

`DevOps` could also use this mechanism to deliver an S1 or S2 solution for projects.

However, it requires updating `kube-state-metrics` configuration and granting it additional read permissions, so it is not directly suitable as an out-of-the-box productized mechanism.

`AIT` currently has no plan to generalize this into a built-in platform feature; we can revisit if demand grows.

### `Tekton` enhancement approach (optional): configurable additional labels {#tekton-enhancement-approach-optional-configurable-additional-labels}

`Tekton`'s built-in metrics already cover common resources (`PipelineRun`, `TaskRun`, `Pipeline`, `Task`, etc.). For some extended scenarios, adding labels to existing metrics can satisfy requirements while minimizing new time series creation.

We can offer a custom configuration that allows users to add labels to existing metrics via `CEL`:

```yaml
customMetricsTags:
  - metric: taskrun_total
    tag: task_type
    # If obj.metadata.labels contains task.tekton.dev/type, use its value; otherwise use "unknown".
    tagValueCEL: |
      has(obj.metadata.labels["task.tekton.dev/type"])
        ? obj.metadata.labels["task.tekton.dev/type"]
        : "unknown"
```

**This mechanism requires modifying the source code of components that provide native metrics, such as tekton-pipelines and tekton-triggers.**

This mechanism is optional, because the `kube-state-metrics` approach for adding metrics already meets customer needs. We can choose not to implement it initially and add it later if needed to avoid over-design.

Adding tags to existing metrics is mainly a storage-cardinality consideration with limited overall benefit; we can instead add a dedicated metric for the current scenario.

The discussion of this mechanism is mainly to add another implementation option, making it easier to analyze based on real project conditions later:

1. If we later identify a strong demand for adding tags, we can implement it using the current approach.
2. If we later find many projects need new metrics and the current `AIT` S2 solution is limited or hard to configure, we can submit a request to `AIT`.

## Alternatives

- Adopt an `Elasticsearch` + `Kibana`-first solution for metrics storage and visualization.
- Use only `kube-state-metrics` custom metrics for all missing observability requirements.
- Patch `Tekton` upstream directly (higher long-term maintenance cost).

## Implementation Plan

1. Integrate `Tekton` native metrics with `AIT`'s [`Prometheus` scrape rules](https://confluence.alauda.cn/pages/viewpage.action?pageId=184355675).
   - Ship a `ServiceMonitor` `CR` with the `Operator` to register `Prometheus` scrape rules.
   - This item is tracked by another `Jira`: [DEVOPS-42394](https://jira.alauda.cn/browse/DEVOPS-42394)
2. Provide graphs based on native metrics.
   - Integrate with `AIT`'s [custom dashboard](https://confluence.alauda.cn/pages/viewpage.action?pageId=206080421) and ship a `MonitorDashboard` `CR` with the `Operator`.
   - This item is tracked by another `Jira`: [DEVOPS-42394](https://jira.alauda.cn/browse/DEVOPS-42394)
3. Add metrics in `tektoncd-enhancement`.
   - Ship a `ServiceMonitor` `CR` with the `Operator` to register `Prometheus` scrape rules.
   - Based on [tekton trigger metrics](#tekton-triggers-controller-metrics), add scheduledTrigger-related metrics.
   - Add [custom metrics](#metrics-to-add-gaps) to meet project needs.

Long-term plan (implement as needed later):

1. Add more metrics in `tektoncd-enhancement`.
    - Implement the metrics in [Extended graph scenarios](#extended-graph-scenarios).
2. Add graphs based on the new metrics.
    - Implement [Customize graphs](#customize-graphs).
    - Implement the graphs in [Extended graph scenarios](#extended-graph-scenarios).
3. Provide a mechanism to add tags dynamically.
    - Implement this extension mechanism as described in [configurable additional labels](#tekton-enhancement-approach-optional-configurable-additional-labels).
    - Provide product documentation to guide users in configuring custom labels.

### Test Plan

- **Unit**
  - Metric computation logic for any added metrics (if implemented).
  - `CEL` evaluation and fallback behavior for custom labels.
- **Integration**
  - Scraping works with `Prometheus` and `vmagent`.
  - `Dashboard` `CRs` render correctly on `AIT`.
  - Cardinality does not exceed platform expectations under load.
- **End-to-end**
  - Validate dashboards on realistic pipelines (success/failure, long-running tasks, throttling scenarios).
  - Validate counter-reset behavior across controller restarts (`PromQL` `increase()`/`rate()`).

### Infrastructure Needed

- Publishing pipeline for any enhancement components (if implemented).
- Versioned dashboard resources shipped with the product.
