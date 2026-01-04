---
status: proposed
title: Task Overview Template Rendering
creation-date: "2025-11-21"
category: task
authors:
  - "@zichenyu"
---

# TEP-0004: Task Overview Template Rendering

## Summary

[TEP-0003](../0003_pipelinerun_markdown_output.md) introduced markdown results so overview pages could render rich reports that originate from Tekton Tasks. 

During the Sonar Task rollout we learned that Tekton results that rely on termination messages are constrained by the number of containers inside the Pod rather than the frequently cited 4 KB limit.
[Tekton issue #4808](https://github.com/tektoncd/pipeline/issues/4808) confirms that kubelet divides the ~12 KB termination-message budget across all containers, 
so a Sonar run with three steps and three init containers reduces each step's result budget to roughly 2 KB, 
leaving only ~700 bytes for the `overview-markdown` payload once the existing 1.3 KB legacy result and JSON escaping overhead are considered. 

This proposal keeps the markdown workflow for simple reports but adds a ConfigMap-backed template pipeline: 
Tasks emit compact structured metrics while annotations only advertise which ConfigMap (and which result key) should drive rendering. 
The UI picks the markdown result if it exists; otherwise it pulls the template metadata and renders HTML client-side. 
Productized overview reports will leverage the ConfigMap approach by default, 
while catalog Tasks can pick the mode that best fits their payload. Storing templates outside annotations also prevents Tekton from copying ~2 KB blobs into every TaskRun, 
which reduces etcd and Tekton Results/PostgreSQL pressure during repeated executions.

## Motivation

We need to unblock markdown-based overview reports without increasing the Tekton result payload, 
and we want a pattern that other catalog Tasks can reuse whenever they need richer presentations than termination messages allow. 
The same pattern should also produce product-ready templates that clusters can share through ConfigMaps instead of inflating every Task definition.

### Goals

1. Preserve the ability to show Sonar overview reports introduced by TEP-0003 even when the Task has many steps or init containers.
2. Keep Task results within the effective per-container termination message budget.
3. Provide a reusable mechanism so other catalog Tasks can ship opinionated report templates without shipping custom UI code.

### Non-Goals

1. Modify Tekton Pipelines or Kubernetes to increase termination message sizes.
2. Introduce a server-side storage service for arbitrary large reports.
3. Replace custom markdown content that fits inside the current limits.

### Use Cases

1. **Sonar overview**: render a curated HTML report with badges, metrics, and guidance while the Task only emits scan metrics as JSON.

### Requirements

1. **Backward compatibility**: Pipelines that only consume the JSON metrics must continue to work without depending on the UI feature flag.
2. **Template portability**: Templates must be distributable alongside the catalog release (for example via ConfigMaps packaged in operator manifests) so the artifact remains self-contained even though the Task only references it through annotations.
3. **Authoring consistency**: Task authors continue to follow [convention](../../development/catalog/convention.md), which already codifies catalog-wide agreements for annotations, results, and supporting assets.

## Proposal

Two rendering paths coexist:

1. **Markdown result**: Tasks may continue emitting `overview-markdown` for small, fully self-contained reports. This remains the simplest path.
2. **ConfigMap template**: For larger or structured outputs, authors can ship a template inside a shared ConfigMap and return only structured metrics in a Task result (for Sonar we reuse `CODE_SCAN_METRICS`).

We recommend markdown for quick, lightweight summaries and ConfigMaps for complex layouts or Tasks that already emit structured metrics (for example Sonar). 
When both are present, the UI prefers the markdown result. 
If annotations do not specify the ConfigMap selector or the template result key, the renderer skips the template entirely.
If result is missing, the renderer skips the template entirely.

Steps:

1. Define a template data contract that contains metric groups, severity counts, URL links, and localization strings.
2. Publish curated templates via ConfigMaps that the operator can manage centrally.
3. Extend Task definitions so their annotations advertise the ConfigMap label selector and the result key that should feed the template, instead of embedding the HTML directly in the Task.
4. Update the dashboard to detect the annotation, locate the ConfigMap, fetch the template, render it with a conservative templating engine (e.g., [EJS](https://github.com/mde/ejs)), and sanitize the output before injecting it into the DOM.
5. Document how other catalog Tasks can opt in by populating the annotation, shipping a ConfigMap, and producing a compatible result.

We will continue to support both paths when planning catalog Tasks, but the productized default report bundles will use ConfigMap templates so we can support detailed reports.

### Notes and Caveats

- Termination messages are capped at ~12 KB per Pod and divided across containers, so Task results must remain small even when templates move to ConfigMaps.
- UI renderers must strip unsafe HTML to avoid accidental script injection when Tasks pass user-controlled strings.
- The UI component already sanitizes rendered HTML (for example it drops `<script>` tags), which mitigates XSS, but templates should still avoid embedding untrusted fragments.
- Tekton automatically copies Task annotations to TaskRuns, so keeping 2 KB templates inside annotations multiplies etcd storage and creates extra rows/bytes in the Tekton Results PostgreSQL database whenever Pipelines rerun. Using ConfigMaps avoids this replication.
- Task annotations already carry icons of similar size; moving them to ConfigMaps would provide the same storage benefits, but that work will be tracked separately because it requires coordinated front-end changes.

## Design Details

1. **ConfigMap template**

   ```yaml
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: sonarqube-scanner-0.5-overview-template
      # Templates live in the `kube-public` namespace so anyone who can access the pipeline editor page can read them without needing additional per-namespace RBAC.
     namespace: kube-public
     annotations:
       # keep namespace hardcoded to kube-public even when InstallerSets perform ReplaceNamespace
       operator.tekton.dev/preserve-namespace: "true"
     labels:
       # tell the UI which Task this template is for
       style.tekton.dev/overview-template-task: sonarqube-scanner
       # version the template/task pairing (e.g., 0.1, 0.2)
       style.tekton.dev/overview-template-task-version: "0.5"
       # tell the UI what kind of engine to use
       style.tekton.dev/overview-template-engine: ejs
   data:
     # ejs ./template.ejs -f data.json -o ./output.html
     template.ejs: |
       <%
         const data = typeof metrics !== 'undefined' ? metrics : {};
         const asNumber = (value, fallback = 0) => {
           const parsed = Number(value);
           return Number.isFinite(parsed) ? parsed : fallback;
         };
         const clampPercent = (value) => Math.max(0, Math.min(100, asNumber(value)));
         const formatPercent = (value, digits = 1) => `${asNumber(value).toFixed(digits)}%`;
         const bugCount = asNumber(data.bugs);
         const vulnerabilityCount = asNumber(data.vulnerabilities);
         const codeSmellCount = asNumber(data.code_smells);
         const hotspotCount = asNumber(data.security_hotspots);
         const coverage = asNumber(data.coverage);
         const duplication = asNumber(data.duplicated_lines_density);
         const loc = asNumber(data.ncloc);
         const locLabel = data.loc_label || "Lines of Code";
         const qualityStatus = data.alert_status || "UNKNOWN";
         const qualityColor = qualityStatus === "OK" ? "#5c1" : (qualityStatus === "ERROR" ? "#f44" : "#fa0");
         const reportUrl = data.report_url || "";
         const sourceCoverage = asNumber(data.source_branch_coverage ?? data.coverage);
         const sourceDuplication = asNumber(data.source_branch_duplication ?? data.duplicated_lines_density);
         const targetCoverage = asNumber(data.target_branch_coverage ?? data.coverage);
         const targetDuplication = asNumber(data.target_branch_duplication ?? data.duplicated_lines_density);
       %>

       <div style="display:flex;align-items:center;margin:0 0 8px">
           <b>Code Scan Results</b>
           <% if (reportUrl) { %>
               <a style="margin-left:8px" href="<%= reportUrl %>" target="_blank" rel="noreferrer">View Report</a>
           <% } %>
           <span style="margin-left:auto;color:<%= qualityColor %>"><%= qualityStatus %></span>
       </div>

       <div style="display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px;color:#999">
           <div style="flex:1"><b style="color:#f44"><%= bugCount %></b> Bug</div>
           <div style="flex:1"><b style="color:#fa0"><%= vulnerabilityCount %></b> Vulnerability</div>
           <div style="flex:1"><b style="color:#5c1"><%= codeSmellCount %></b> Code Smell</div>
           <div style="flex:1"><b style="color:#f44"><%= hotspotCount %></b> Security Hotspots</div>
           <div style="flex:1"><b style="color:#fe1"><%= formatPercent(coverage) %></b> Coverage</div>
           <div style="flex:1"><b style="color:#09f"><%= formatPercent(duplication) %></b> Duplication Rate</div>
           <div style="flex:1"><b style="color:#5c1"><%= loc.toLocaleString() %></b> <%= locLabel %></div>
       </div>

       <div style="display:flex;gap:16px;color:#666">
           <div style="flex:1">
               <div style="margin:0 0 8px;font-weight:700">Source Branch</div>
               <div>
                   <div style="height:7px;margin:0 0 4px;border:1px solid #ddd">
                       <div style="width:<%= clampPercent(sourceCoverage) %>%;height:100%;background:#5c1"></div>
                   </div>
                   <small>Coverage: <%= formatPercent(sourceCoverage) %></small>
                   <div style="height:7px;margin-top:4px;border:1px solid #ddd">
                       <div style="width:<%= clampPercent(sourceDuplication) %>%;height:100%;background:#999"></div>
                   </div>
                   <small>Duplication: <%= formatPercent(sourceDuplication) %></small>
               </div>
           </div>

           <div style="width:1px;background:#ddd"></div>

           <div style="flex:1">
               <div style="margin:0 0 8px;font-weight:700">Target Branch</div>
               <div>
                   <div style="height:7px;margin:0 0 4px;border:1px solid #ddd">
                       <div style="width:<%= clampPercent(targetCoverage) %>%;height:100%;background:#5c1"></div>
                   </div>
                   <small>Coverage: <%= formatPercent(targetCoverage) %></small>
                   <div style="height:7px;margin-top:4px;border:1px solid #ddd">
                       <div style="width:<%= clampPercent(targetDuplication) %>%;height:100%;background:#999"></div>
                   </div>
                   <small>Duplication: <%= formatPercent(targetDuplication) %></small>
               </div>
           </div>
       </div>
   ```


2. **Task annotations**

   ```yaml
   metadata:
     annotations:
       style.tekton.dev/overview-template-selector: "style.tekton.dev/overview-template-task=sonarqube-scanner,style.tekton.dev/overview-template-task-version=0.5"
       style.tekton.dev/overview-template-result-key: CODE_SCAN_METRICS
   ```

   - `overview-template-selector` tells the UI which ConfigMap to fetch.
   - `overview-template-result-key` identifies the Task result that carries the structured metrics. When it is empty or missing, the renderer skips template rendering.
   - If `overview-markdown` is present, the UI prefers it over the template path, because we need to give priority to displaying the templates directly output by users.
   - If the specified result is missing, the renderer skips the template entirely.
   - Proposed: allow multiple results, comma-separated, so Tasks that split outputs across several results can still render one template. The UI will load each listed result, merge them into a JSON object keyed by result name, and pass that merged payload to the template engine (string, array, and object values are all supported). Example:

     ```yaml
     metadata:
       annotations:
         style.tekton.dev/overview-template-selector: "style.tekton.dev/overview-template-task=sonarqube-scanner,style.tekton.dev/overview-template-task-version=0.5"
         style.tekton.dev/overview-template-result-key: CODE_SCAN_METRICS,CODE_SCAN_TRENDS
         style.tekton.dev/overview-template-result-aliases: CODE_SCAN_METRICS:metrics,SCAN_RESULT_URL,SCAN_PROJECT
     ---
     # Task results (conceptual)
     - name: CODE_SCAN_METRICS
       value: 
         bugs: "2"
         vulnerabilities: "1"
     - name: SCAN_RESULT_URL
       value: "https://devops-sonar.alaudatech.net/dashboard?id=sonar-project-20251125-24357&branch=main"
     - name: SCAN_PROJECT
       value: 
         - foo
         - bar
     ---
     # UI merged payload provided to the template
     # metrics is an alias for CODE_SCAN_METRICS, which is defined in annotation
     {
       "metrics": {
         "bugs": "2",
         "vulnerabilities": "1"
       },
       "SCAN_RESULT_URL": "https://devops-sonar.alaudatech.net/dashboard?id=sonar-project-20251125-24357&branch=main",
       "SCAN_PROJECT": [
         "foo",
         "bar"
       ]
     }
     ```

3. **Result schema**

   ```yaml
   alert_status: OK
   bugs: "0"
   code_smells: "0"
   coverage: "0"
   duplicated_lines: "0"
   duplicated_lines_density: "0"
   languages: "[java xml]"
   lines_to_cover: "6"
   maintainability_rating: "1"
   maintainability_rating_class: A
   ncloc: "89"
   ncloc_language_distribution: java,xml
   new_bugs: ""
   new_code_smells: ""
   new_coverage: ""
   new_duplicated_lines: ""
   new_duplicated_lines_density: ""
   new_lines_to_cover: ""
   new_security_hotspots: ""
   new_vulnerabilities: ""
   reliability_rating: "1"
   reliability_rating_class: A
   security_hotspots: "0"
   security_rating: "1"
   security_rating_class: A
   security_review_rating: "1"
   security_review_rating_class: A
   sqale_rating: ""
   vulnerabilities: "0"
   ```

   This mirrors the current Sonar Task output, stays below 2 KB, and drives the template via simple key interpolation.

4. **UI rendering**

   - Fetch TaskRun annotations via the Kubernetes API the UI already uses for step details.
   - Execute the ConfigMap template with [EJS](https://github.com/mde/ejs) inside an isolated sandbox so it only receives the Task result (`CODE_SCAN_METRICS`) plus helper utilities, preventing access to `window`, network calls, or other globals.

5. **ConfigMap lifecycle and distribution**

   - Templates ship with the catalog release and do not need historical retention, so the ConfigMap is owned and reconciled by the TektonInstallerSet; upgrades replace the ConfigMap instead of keeping older revisions.
   - Because templates are tightly coupled to catalog Tasks, the ConfigMap manifest lives in the catalog repository and is synced via the component framework described in [Operator Integration Guide](../../development/component-upgrade-guide/operator-integration.md).
   - Publish the ConfigMap artifact from the catalog to [Nexus](https://build-nexus.alauda.cn/#browse/browse:alauda:devops%2Ftektoncd-releases%2Fcatalog) as part of the existing catalog release pipeline.
   - Define a `catalog` component under `components.yaml` with `local_path: tekton-hub/api`, so the ConfigMap is packaged with the Tekton Hub assets and deployed by the same TektonInstallerSet that rolls out Tekton Hub.
   
     ```yaml
     ## catalog component
     catalog:
       revision: main
       releases:
         - remote_path: catalog
           local_path: tekton-hub/api
           local_name: catalog.yaml
     ```
   
     ```shell
     ## upload catalog to nexus
     echo "⚙️ ===> values.yaml content"
     cat values.yaml
  
     echo "⚙️ ===> release artifacts"
     export NEXUS_USERNAME=`cat $(workspaces.secret.path)/username`
     export NEXUS_PASSWORD=`cat $(workspaces.secret.path)/password`
     export OUTPUT_FILE=$(results.array-result.path)
     export BRANCH=$(params.git-revision)
     export COMMIT_ID=$(params.git-commit)
     export REPO=catalog
     export SOURCE_DIR="config"
     build-releases.sh
     cat $OUTPUT_FILE
     ```

## Design Evaluation

### Reusability

Shipping templates via labeled ConfigMaps means catalog Tasks can opt in without bloating CRDs, and operators can patch templates without redeploying Tasks. The JSON schema is intentionally generic (metrics array plus metadata) so scanners, linters, or license checkers can reuse it.

### Simplicity

Task authors only add two annotations and emit structured metrics. Front-end work is limited to reading annotations and rendering a simple template. No external storage or controllers are required.

### Flexibility

Templates can be swapped per ConfigMap revision or label change, and the renderer can provide defaults when annotations are absent. Structured metrics also allow other consumers (CLI, APIs) to repurpose the same data.

### Conformance

The change does not modify Tekton CRDs. Tasks keep using vanilla results and annotations, so we stay within Tekton's supported extension points.

### User Experience

Overview pages regain rich Sonar summaries and do not display escaped HTML entities. Other Tasks gain a consistent pattern for exposing structured reports, while simple scenarios can keep the markdown-only workflow.

### Performance

Templates are cached per Task definition and fetched once per unique Task UID, so runtime overhead is negligible. Smaller results also marginally reduce etcd storage and API payloads.

### Risks and Mitigations

- **Template drift**: Task updates might ship incompatible templates. Mitigation: version annotations and validate JSON keys before rendering.
- **Security**: Inserting HTML introduces XSS risks. Mitigation: sanitize interpolation results and disallow inline scripts/styles.

### Drawbacks

- Dashboard code becomes slightly more complex because it must fetch annotations and run a template engine.
- Template authorship adds maintenance overhead whenever we tweak Sonar metrics.

## Alternatives

1. **Compress markdown results**: Base64-compressing markdown would still hit termination message limits and adds decoding complexity for every consumer.
2. **Write HTML to ConfigMaps**: Requires extra RBAC, extra clean-up logic, and does not scale for short-lived tasks.
3. **Increase Pod termination message size**: Needs Kubernetes or Tekton changes and is outside our control.
4. **Store reports in artifacts**: Persisting artifacts in object storage solves size limits but demands shared infrastructure and slows down rendering.

## Implementation Plan

1. Update Tasks specs in the catalog to add the template annotations, emit `CODE_SCAN_METRICS`, and publish the cluster-scoped ConfigMap containing the template.
2. Reuse the existing catalog → tektoncd-operator sync path (publish artifacts to Nexus, then run `make update-components`) so ConfigMaps live in the operator repository alongside other components.
3. Teach the dashboard overview page to load templates based on label selectors, render metrics, and fall back to markdown when unavailable.
4. Produce two deliverables if this TEP is approved: (a) a customer-facing guide describing how to enable the feature and choose between markdown and ConfigMap templates, and (b) a developer convention doc at [convention](../../development/catalog/convention.md) that codifies Task authoring rules (catalog contributors already agreed to follow this convention).
5. Add feature flags so operators can enable the renderer incrementally while keeping markdown as the default fallback.

### Test Plan

- Backend integration tests validate that Tasks emit the expected structured result payload (e.g., `CODE_SCAN_METRICS`), ensuring keys and types match the contract.
- Templates live in the backend repo, and backend integration tests run the `ejs` CLI against every template to ensure they render successfully. Frontend E2E mainly covers the basic template rendering/display path.
- Backend E2E does not need to assert the ConfigMap presence because frontend E2E already exercises template retrieval and rendering.

### Infrastructure Needed

No new cluster-side infrastructure is needed. Existing dashboard instances require access to TaskRun annotations, which they already possess.

## References

1. [Kubernetes termination messages](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination) - documents the ~12 KB Pod-level limit enforced by kubelet.
2. [TEP-0003: PipelineRun Support Markdown Output](../0003_pipelinerun_markdown_output.md) - original markdown report design and constraints.
