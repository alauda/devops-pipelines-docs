---
title: PipelineRun Support Markdown Output
authors:
  - zcyu@alauda.io
creation-date: 2025-09-25
last-updated: 2025-09-25
status: proposed
---

# TEP-0003: PipelineRun Support Markdown Output

## Record of Changes

| Order | Change of Content                              | Reason for Change         | Change Time | Change Executor | Approved By      |
|:------|:-----------------------------------------------|:--------------------------|:------------|:----------------|:-----------------|
| 1     | Design: PipelineRun Support Markdown Output    | publish                   | 2025-09-25  | zcyu@alauda.io  | bozhou@alauda.io |
| 2     | Add Conclusion and Non-Functional Requirements | add discussion conclusion | 2025-09-28  | zcyu@alauda.io  | bozhou@alauda.io |

## Summary

The Tekton PipelineRun details page should allow users to view a summary of an execution report. 
This document describes the design for displaying **markdown-formatted** reports on the pipeline overview page.

## Motivation

Currently, users can only write task execution results to the pipeline **results**, 
and they cannot quickly understand task outcomes on the overview page. 
We need a custom report output capability so users can display task results as markdown on the overview page.

### Goals

- The overview page supports displaying **markdown** reports.
- Users can output a custom report within a **Task**.
- Reports remain visible on the overview page even when the PipelineRun **fails**.

### Non-Goals

- Provide report output templates.
- Support unlimited report size.

## Design Details

### Constraints

Writing Tekton Pipeline **results** has the following constraints:

1. Only when the **Task** referenced by a **Pipeline result** succeeds (including **finally** tasks) will that result be written to the PipelineRun.
2. If the referenced **Task** fails, although the **TaskRun** `status.results` will still be written, the **PipelineRun** `status.results` will **not** include that result.

Tekton considers results produced by failed tasks to be unreliable and therefore not suitable as pipeline-level results.

In earlier versions, TaskRuns also did not emit such results, and subsequent tasks could not reference them. That issue was resolved by [#6510 feat: support to produce results from a failed task](https://github.com/tektoncd/pipeline/pull/6510).

However, pipeline results still cannot reference failed tasks. This issue remains open and currently has no community PR that fully addresses it: [#3749 Publish results when task and pipeline runs fail](https://github.com/tektoncd/pipeline/issues/3749).

### Proposal

We considered the following approaches to work around the above limitations (**recommended: 1 and 2**):

1. **Use a `finally` task to output a result.**
2. **Read reports directly from `TaskRun` results.**
3. Pass the report via a **workspace** and print it in a `finally` task log.
4. Modify Tekton source code so pipeline results can pull values from **failed** tasks.

#### Option 1: Output the result via a `finally` task

Assume the task that produces the report is named `scan`:

1. Add a `finally` task named `report`, which reads the `scan` task's result and writes it to its own result. This task must succeed.
2. Configure pipeline results to reference the `report` task, e.g. `$(finally.report.results.string-result)`.
3. In the pipeline editor UI, let users specify which results to treat as reports (for example, via an annotation like `style.tekton.dev/reports-in-results: [report1, report2]`).

This way, a **guaranteed-success** `report` task circumvents the limitation that the pipeline cannot read results from a failed task—without changing the PipelineRun's overall status (if `scan` fails, the PipelineRun still fails).

**Points to note:**

1. If `scan` is configured with `onError: continue`, consider adding an `exit` `finally` task that runs **only** when `$(tasks.scan.status)` is `Failed`, and simply `exit 1`.
2. The UI currently does not allow selecting results from **finally** tasks; we need to fix the validation rule (error: `The result value must match the expression $(tasks..*.results..*)`).

**Advantages**

1. Minimal work: mainly implement the overview-page rendering for markdown reports.
2. Aligns with Tekton's design: PipelineRun results originate from successful tasks.

**Disadvantage**

1. Some user configuration overhead: users must add a `finally` task, which could be confusing.
2. Multiple reporting tasks may require multiple `finally` tasks.
3. Single Task result size is capped at **4 KB**.

#### Option 2: Read reports from `TaskRun` results

Assume the report-producing task is `scan`.

Add report collection settings to the pipeline editor and store them in annotations, e.g., to read `string-result` from the `scan` task:

1. `style.tekton.dev/reports-scan-display-name: SonarQube Scan Report`
2. `style.tekton.dev/reports-scan-result: string-result`

On the PipelineRun overview page:

1. Parse the collection rules from annotations.
2. Based on the specified `pipelineTaskName`, find the corresponding **TaskRun** from `status.childReferences`.
3. Read the report from the TaskRun's referenced **result**.

Here is an example of the PipelineRun annotations and `status.childReferences`:

```yaml
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  annotations:
    style.tekton.dev/reports-scan-display-name: SonarQube Scan Report
    style.tekton.dev/reports-scan-result: string-result
status:
  childReferences:
    - apiVersion: tekton.dev/v1
      kind: TaskRun
      name: result-test-pfqzz-scan
      pipelineTaskName: scan
    - apiVersion: tekton.dev/v1
      kind: TaskRun
      name: result-test-pfqzz-report
      pipelineTaskName: report
```

**Advantages**

1. Less user configuration: only specify the **Task** and the **result** key.
2. Annotations offer good extensibility for future report customization options.

**Disadvantage**

1. Requires FE work: the UI needs to read from **TaskRun** results.
2. CLI users cannot read the report directly from the PipelineRun, which may be a suboptimal experience (this feature primarily targets UI users).
3. Single Task result size is capped at **4 KB**.

#### Option 3: Output the report via a workspace

Assume the report-producing task is `scan`:

1. Add a `finally` task named `report` that mounts the **same workspace** as `scan`.
2. The `scan` task writes the report into that workspace; the `report` task prints the report to logs.
3. The overview page reads the report content from the `report` task's logs.

**Advantages**

1. Suitable for **long text**: the workspace size is configurable and not limited to 4 KB.

**Disadvantage**

1. Requires an extra workspace to pass the report.
2. Logs may be cleaned up, causing the report to be lost.

#### Option 4: Modify Tekton source code

Change Tekton so that a pipeline result can reference outputs from **failed** tasks.

Although the community has requested this ([#3749](https://github.com/tektoncd/pipeline/issues/3749)), it is still unresolved. To date, only the ability for **failed TaskRuns** to **emit and pass** results has been merged ([#6510](https://github.com/tektoncd/pipeline/pull/6510)).

The official stance is that results from failed tasks are unreliable and should not be surfaced as pipeline-level results. It is possible this will not be prioritized upstream. Implementing and maintaining a fork that changes core Tekton Pipeline behavior would incur non-trivial effort and upgrade burden.

**Recommendation:** prioritize the other approaches first, and dive deeper into this option only if necessary.

## Conclusion

1. **Adopt Option 2:** The frontend should read the report **directly from TaskRun results** and render it on the **Summary** tab.
2. **Standardize a result key:** Agree on a specific result key (e.g., **`markdown`**, type **string**). Tasks write the markdown-formatted report to this result.
3. **Render across TaskRuns:** On the PipelineRun **Summary** page, the frontend iterates over all **TaskRuns**; if the specified result is non‑empty, render it as **markdown**.
4. **Future formats:** If other report formats are needed later, introduce additional **well-named result keys** accordingly.
5. **With Tekton Results:** When **tekton-results** is deployed and a **TaskRun** has been garbage‑collected, the UI must support fetching the archived **results** to continue rendering the report.

## Non-Functional Requirements

### Performance
- The Summary tab should load within **P50 ≤ 1.5s** and **P95 ≤ 3s** for PipelineRuns with ≤ 20 TaskRuns; for larger runs, render progressively as data arrives.
- Fetch TaskRun `status.results` concurrently with request de-duplication; cache per-PipelineRun results for ~30 seconds to reduce API QPS.
- Respect Tekton per-result size limits (≤ 4 KB per Task result). The UI should cap aggregated render size to ~64 KB and clearly indicate when content is truncated.

### Reliability
- Primary data source is TaskRun `status.results`. If TaskRuns have been garbage-collected and **tekton-results** is available, fall back to archived data.
- Even when the PipelineRun **fails**, surface available reports from failed TaskRuns.
- Apply bounded retries with exponential backoff on API calls; on persistent errors, degrade gracefully by showing partial content with actionable error details.

### Security
- Enforce namespace-scoped RBAC: only users with `get/list` permission on TaskRuns can view reports; do not broaden privileges.
- Sanitize Markdown strictly (no inline HTML or scripts; external links opened safely; images disabled unless explicitly allowed).
- Mask obvious secrets/tokens in rendered content and avoid writing sensitive data to caches or logs.
- Emit audit entries for viewing/report access (timestamp, actor, resource).

### Usability
- Card-per-TaskRun presentation showing task name, status, timing, and data source (live vs. archive).
- Support headings, lists, tables, code blocks, and inline code; provide a one-click copy action; collapse long sections.
- Provide skeleton loading, clear error cards, and “truncated” indicators; ensure keyboard accessibility, internationalization, and dark-mode readiness.

### High Availability
- Target feature-level availability of **≥ 99.9% per month** (successful Summary tab load as the SLI).
- Stateless components with horizontal scaling; health probes enabled; sensible timeouts and circuit breakers.
- If dependencies (K8s API or tekton-results) are degraded, continue in a read-only/partial mode using cached or already-fetched data.

### Data Migration
- Not involved for this feature.
