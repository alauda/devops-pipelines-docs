---
status: proposed
title: Helm Chart Packaging and OCI Push Pipeline
creation-date: "2025-09-26"
category: docs
authors:
  - "@zichenyu"
---

# TEP-0003: Helm Chart Packaging and OCI Push Pipeline

- [Summary](#summary)
- [Motivation](#motivation)
  - [Goals](#goals)
  - [Non-Goals](#non-goals)
  - [Use Cases](#use-cases)
  - [Requirements](#requirements)
- [Proposal](#proposal)
  - [Notes and Caveats](#notes-and-caveats)
- [Design Details](#design-details)
  - [Pipeline Parameters](#pipeline-parameters)
  - [Workspaces](#workspaces)
  - [Results](#results)
  - [Example PipelineRuns](#example-pipelineruns)
    - [Example A — Minimal Public to Public](#example-a--minimal-public-to-public)
    - [Example B — Private Registry Auth via Registry Config](#example-b--private-registry-auth-via-registry-config)
    - [Example C — Custom CA + Version Override + Overwrite](#example-c--custom-ca--version-override--overwrite)
- [Design Evaluation](#design-evaluation)
  - [Reusability](#reusability)
  - [Simplicity](#simplicity)
  - [Flexibility](#flexibility)
  - [Conformance](#conformance)
  - [User Experience](#user-experience)
  - [Performance](#performance)
  - [Reliability](#reliability)
  - [Security](#security)
  - [Usability](#usability)
  - [High Availability](#high-availability)
  - [Data Migration](#data-migration)
  - [Risks and Mitigations](#risks-and-mitigations)
  - [Drawbacks](#drawbacks)
- [Alternatives](#alternatives)
- [Implementation Plan](#implementation-plan)
  - [Test Plan](#test-plan)
  - [Infrastructure Needed](#infrastructure-needed)
  - [Upgrade and Migration Strategy](#upgrade-and-migration-strategy)
  - [Implementation Pull Requests](#implementation-pull-requests)
- [References](#references)
<!-- /toc -->

## Summary {#summary}

This TEP proposes a Tekton Pipeline that automates packaging a Helm Chart from a Git repository and pushing the resulting artifact to an OCI registry. The pipeline supports private repository authentication, dependency build, version override, configurable TLS/CA handling, a **common contract for workspaces and results**, structured status, and basic idempotency and retry semantics.

## Motivation {#motivation}

Organizations often need a repeatable, observable, and secure path to move Helm Charts from source control to an OCI registry. Manually executing `helm dependency build`, `helm package`, and `helm push` is error‑prone, lacks standardized observability, and complicates policy enforcement (RBAC, CA, TLS). A **common contract** for workspaces and results makes this pipeline easy to adopt across teams and UIs.

### Goals {#goals}

- Fetch chart sources from HTTP(S)/SSH Git with `repoUrl`/`revision`.
- Optionally build chart dependencies (`helm dependency build`).
- Package charts with optional `versionOverride` and pass‑through `packageArgs`.
- Push artifacts to an OCI repo (e.g., `oci://host/org/repo`) with optional overwrite control.
- Support custom CA bundles and _explicit_ TLS skip for controlled environments.
- Emit **standardized results** (`artifact.*`, `status.*`, `summary-json`) for diagnosability and UI consumption.
- Provide bounded retries and predictable behavior under concurrency.

### Non-Goals {#non-goals}

- Managing non-Helm packaging formats.
- Replacing enterprise artifact policies or full supply‑chain signing/scanning (only referenced as optional enhancements).
- Implementing a dedicated triggers/PR automation system (manual `PipelineRun` is sufficient; external CI can orchestrate).

### Use Cases {#use-cases}

- Push internal charts into a private OCI registry with credentials mounted through `kubernetes.io/dockerconfigjson`.
- Environments with private CAs where the build and push steps must trust custom certificates.
- Release workflows that need a temporary `versionOverride` without mutating the Git source.
- Multi‑tenant namespaces requiring strict RBAC and minimal credential exposure.

### Requirements {#requirements}

**Functional**
- Support Git checkout, dependency build, packaging, and OCI push.
- Allow overwrite only when explicitly enabled.
- Output artifact identity and location in results; log structured error codes.

**Operational/Performance (SLOs)**
- P50 total latency ≤ 90s and P95 ≤ 180s for small/medium charts under normal network conditions.
- Sustain ~20 concurrent PipelineRuns per cluster without >30% P95 degradation (given namespace quotas).
- Default resource requests/limits per step: CPU 200m/1, Memory 128Mi/512Mi; P95 memory < 300Mi.

**Security**
- Minimal RBAC; credential isolation; non‑root, read‑only filesystem; no privilege escalation.
- TLS verification on by default; CA injection supported; TLS skip only in controlled/sandbox environments.

## Proposal {#proposal}

The pipeline comprises four primary stages:

1. **Git Checkout** — Clone sources from `repoUrl` at `revision` (default `main`). Clear failure modes for auth, branch not found, and network issues.
2. **Dependency Build** — When `dependencyUpdate=true`, run `helm dependency build` and surface diagnostic logs.
3. **Package** — Run `helm package` on `chartPath`; validate `Chart.yaml` (`name`, `version`). When `versionOverride` is set, operate on a temporary copy to avoid mutating the repo. Emit the output chart path and `(name, version)` to results.
4. **OCI Push** — Use `helm push` (OCI) to `ociRepo:version`. Use login credentials from `registry-config` workspace (registry config) or `helm registry login`. Deny overwrite by default; enable `--force` when `allowOverwrite=true`. Emit `artifact.ref` and `artifact.digest` on success (digest is best‑effort if the registry reports it). A `finally` step populates `status.*` and `summary-json` regardless of success/failure.

### Notes and Caveats {#notes-and-caveats}

- **TLS** — `insecureSkipTLSVerify` is for _non‑production_ only. Prefer CA injection via `custom-ca` workspace; enforce policy to reject TLS skip in production namespaces.
- **Idempotency** — Overwrite requires explicit opt‑in to avoid accidental clobbering.
- **Observability** — Emit step durations, redacted parameter snapshots, and typed error codes such as `AUTH_GIT`, `DEP_BUILD_FAIL`, `CHART_INVALID`, `PACKAGE_FAIL`, `AUTH_OCI`, `PUSH_CONFLICT`, `NETWORK`.

## Design Details {#design-details}

### Pipeline Parameters {#pipeline-parameters}

| Name                    | Type   | Required | Default   | Description                                               |
|-------------------------|--------|----------|-----------|-----------------------------------------------------------|
| `repoUrl`               | string | Yes      | —         | HTTPS/SSH Git repository URL.                             |
| `revision`              | string | No       | `main`    | Branch, tag, or commit.                                   |
| `chartPath`             | string | Yes      | —         | Relative path to the chart inside the repo.               |
| `ociRepo`               | string | Yes      | —         | Target repo, e.g., `oci://host/org/repo`.                 |
| `versionOverride`       | string | No       | `""`      | Temporarily overrides `Chart.yaml` version for packaging. |
| `packageArgs`           | string | No       | `""`      | Extra args passed to `helm package`.                      |
| `allowOverwrite`        | string | No       | `"false"` | Allow overwriting an existing version in the registry.    |
| `dependencyUpdate`      | string | No       | `"true"`  | Run `helm dependency build`.                              |
| `insecureSkipTLSVerify` | string | No       | `"false"` | Skip TLS verification (non‑prod only).                    |

### Workspaces {#workspaces}

| Name              | Required | Purpose                                                                                                                              |
|-------------------|----------|--------------------------------------------------------------------------------------------------------------------------------------|
| `source`          | Yes      | Main working directory for checkout, build cache, and packaging outputs.                                                             |
| `registry-config` | No       | Registry config for OCI auth (expects `.docker/config.json` layout, typically from a Secret of type `kubernetes.io/dockerconfigjson`). |
| `custom-ca`       | No       | One or more PEM files to be merged into system trust for Git/OCI (e.g., `ca.crt`, `bundle.pem`).                                     |
| `config`          | No       | Optional workspace for custom configs.                                                                                               |
| `secret`          | No       | Optional workspace for custom secrets.                                                                                               |

### Results {#results}

| Name               | Example                                     | Description                                                |
|--------------------|---------------------------------------------|------------------------------------------------------------|
| `artifact.name`    | `mychart`                                   | Chart name from `Chart.yaml`.                              |
| `artifact.version` | `1.2.3`                                     | Resolved version (from `Chart.yaml` or `versionOverride`). |
| `artifact.file`    | `/workspace/source/mychart-1.2.3.tgz`       | Absolute path to packaged chart inside workspace.          |
| `artifact.ref`     | `oci://registry.example.com/org/repo:1.2.3` | OCI reference (repo + tag).                                |
| `artifact.digest`  | `sha256:deadbeef...`                        | OCI digest if available (best‑effort).                     |
| `status.code`      | `OK` or `AUTH_GIT`/`PACKAGE_FAIL`/...       | Final status code. Always populated by a `finally` step.   |
| `status.message`   | `Packaged and pushed successfully.`         | Short human‑readable message (≤ 1024 chars).               |
| `summary-json`     | `{"name":"mychart","version":"1.2.3",...}`  | Compact JSON with the above fields for UI consumption.     |

### Example PipelineRuns {#example-pipelineruns}

> Replace `namespace`, URLs, and Secret/ConfigMap names with your environment specifics.

#### Example A — Minimal Public to Public {#example-a--minimal-public-to-public}

```yaml
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: helm-oci-push-minimal
  namespace: dev
spec:
  pipelineRef:
    name: helm-oci-push-pipeline
  params:
    - name: repoUrl
      value: https://github.com/example/mycharts.git
    - name: revision
      value: main
    - name: chartPath
      value: charts/myapp
    - name: ociRepo
      value: oci://registry.example.com/helm
    - name: dependencyUpdate
      value: "true"
  workspaces:
    - name: source
      emptyDir: {}
# Results to expect (names are stable under contract v1):
#   artifact.name, artifact.version, artifact.file, artifact.ref, artifact.digest,
#   status.code, status.message, summary-json
```

#### Example B — Private Registry Auth via Registry Config {#example-b--private-registry-auth-via-registry-config}

```yaml
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: helm-oci-push-private-reg
  namespace: dev
spec:
  pipelineRef:
    name: helm-oci-push-pipeline
  params:
    - name: repoUrl
      value: https://github.com/example/mycharts.git
    - name: revision
      value: release-1.0
    - name: chartPath
      value: charts/enterprise-app
    - name: ociRepo
      value: oci://harbor.internal.example.com/dev/helm
  workspaces:
    - name: source
      emptyDir: {}
    - name: registry-config
      secret:
        secretName: harbor-registryconfigjson
        items:
          - key: .dockerconfigjson
            path: config.json
```

#### Example C — Custom CA + Version Override + Overwrite {#example-c--custom-ca--version-override--overwrite}

```yaml
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: helm-oci-push-custom-ca
  namespace: dev
spec:
  pipelineRef:
    name: helm-oci-push-pipeline
  params:
    - name: repoUrl
      value: https://git.internal.example.com/team/charts.git
    - name: revision
      value: v1.2.3
    - name: chartPath
      value: charts/payments
    - name: ociRepo
      value: oci://registry.internal.example.com/platform/helm
    - name: versionOverride
      value: "1.2.3+build.4"
    - name: allowOverwrite
      value: "true"
    - name: dependencyUpdate
      value: "false"
    - name: insecureSkipTLSVerify
      value: "false"
  workspaces:
    - name: source
      emptyDir: {}
    - name: registry-config
      secret:
        secretName: internal-registry-auth
        items:
          - key: .dockerconfigjson
            path: config.json
    - name: custom-ca
      configMap:
        name: private-ca-bundle
        items:
          - key: ca.crt
            path: ca.crt
```

## Design Evaluation {#design-evaluation}

### Reusability {#reusability}

Leverages common Tekton tasks/steps for Git, Helm, and OCI. Can be composed with optional supply‑chain tasks (signing, SBOM, scan).

### Simplicity {#simplicity}

Single pipeline with a linear flow. Defaults minimize configuration while exposing parameters for advanced use.

### Flexibility {#flexibility}

Supports both HTTPS and SSH Git, standard Helm OCI registries, optional dependency build, and optional overwrite. CA injection enables air‑gapped or private PKI.

### Conformance {#conformance}

No Tekton API changes. Works with standard Kubernetes objects and Helm commands. Surface results via Tekton Results for UIs/dashboards.

### User Experience {#user-experience}

UI can read **summary-json** or the discrete `artifact.*` and `status.*` results. Error codes improve triage and on‑call handoffs.

### Performance {#performance}

- End-to-end execution remains bounded and observable; parallelize independent steps (fetch, package, push) where safe.
- Respect registry/API rate limits; enable short-lived caching to avoid repeated fetches; progressive logs for long pushes.

### Reliability {#reliability}

- Bounded retries with exponential backoff for transient Git/OCI/network errors; fail fast on permanent errors (e.g., bad credentials).
- Always publish final results in a `finally` task (`status.code`, `status.message`, `summary-json`) to keep UI signals deterministic.
- Idempotent packaging path and an explicit `allowOverwrite` parameter avoid accidental duplication and make re-runs safe.

### Security {#security}

- Least-privilege RBAC; mount secrets only to steps that need them; run as non-root with a read-only root filesystem.
- TLS verification is enabled by default (custom CA supported); do not echo credentials in logs.
- Optional hardening (signing, SBOM, scanning) can be composed as adjacent steps without changing the contract.

### Usability {#usability}

- Stable outputs (`artifact.*`, `status.*`, `summary-json`) for dashboards/CLI; clear, typed error codes to speed up triage.
- Provide minimal examples for common auth/TLS/overwrite scenarios; parameters and defaults aim for least surprise.

### High Availability {#high-availability}

- Pipeline runs are stateless and horizontally scalable; no single in-pipeline SPOF.
- On dependency degradation (e.g., registry hiccups), surface actionable errors; safe to re-run due to idempotency.

### Data Migration {#data-migration}

- Not applicable for this feature.

### Risks and Mitigations {#risks-and-mitigations}

- **TLS Skip Misuse** — Enforce via admission policies; document redlines.  
- **Credential Exposure** — Mount secrets only to steps that need them; redact logs; avoid persisting credentials in env vars.  
- **Overwrite Accidents** — Default deny; require `allowOverwrite=true`.  
- **Chart Invalid** — Validate `Chart.yaml` and fail fast with actionable logs.  
- **Network Flakiness** — Bounded retries with backoff for transient errors.

### Drawbacks {#drawbacks}

- Helm/OCI tooling must be present in the step images.  
- Private CAs and air‑gapped registries add operational complexity.

## Alternatives {#alternatives}

- Use non‑OCI Helm repositories (index.yaml + object storage) — less aligned with modern OCI workflows.  
- Run packaging in external CI (e.g., GitHub Actions) — loses in‑cluster policy controls and K8s‑native observability.  
- Use ORAS directly — viable, but Helm OCI integrates metadata and is widely supported.

## Implementation Plan {#implementation-plan}

1. **MVP** — Git checkout, optional dependency build, package, push; results and error codes; minimal RBAC.  
2. **Hardening** — CA injection, resource limits, retries, admission policies for TLS skip.  
3. **Enhancements (optional)** — signing (cosign/helm provenance), SBOM (syft), vulnerability scan (trivy), and UI surfacing.

### Test Plan {#test-plan}

- **Unit/Step Tests** — verify parameter validation, version override on a temp copy, and results emission.  
- **Integration** — end‑to‑end PipelineRuns against a test registry (with and without auth).  
- **Failure Injection** — invalid credentials, missing branch, network timeouts, push conflicts.  
- **Security** — ensure secrets not logged, container runs as non‑root with read‑only root FS.  
- **Performance** — measure P50/P95 time; load test with ~20 concurrent runs.  
- **TLS/CA** — verify CA merge; ensure TLS skip is blocked in production namespaces (policy test).

### Infrastructure Needed {#infrastructure-needed}

- Access to an OCI registry for testing.  
- Namespace with quotas and metrics collection (e.g., Prometheus/metrics‑server).  
- Admission policy engine (e.g., OPA/Gatekeeper) for TLS skip governance (optional but recommended).

### Upgrade and Migration Strategy {#upgrade-and-migration-strategy}

We version the pipeline as a **product** using semantic versioning (SemVer).

- The Pipeline object MUST set `metadata.labels.app.kubernetes.io/version` and `metadata.annotations.pipeline.alauda.io/contract-version` (this doc uses `contract-version: "1"`).
- **Breaking changes** (e.g., parameter rename/type change, workspace/result rename/removal, behavior change) REQUIRE a **MAJOR** version bump (e.g., `v2.0.0`). A migration guide MUST be published as `MIGRATION-v{MAJOR}.md` with concrete steps and examples.
- **Additive changes** (new optional params/results, non‑breaking behavior) use **MINOR** version bumps.
- **Fixes** and internal changes use **PATCH** bumps.
- Old major versions SHOULD be maintained with security/backport patches for a deprecation window (recommended 6–12 months), documented in release notes.

### Implementation Pull Requests {#implementation-pull-requests}

1. Task implementation and integration test PR
2. Documentation and examples PR

## References {#references}

- [Helm OCI documentation](https://helm.sh/docs/topics/registries/)  
- [Tekton Pipelines documentation](https://tekton.dev/docs/pipelines/pipelines/)
