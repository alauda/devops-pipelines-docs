---
status: proposed
title: Catalog Task Rendering for Unified Shared Script Maintenance
creation-date: "2026-04-07"
category: task
authors:
  - "@zichenyu"
---

# TEP-0006: Catalog Task Rendering for Unified Shared Script Maintenance

## Summary

This proposal introduces template-based rendering for catalog Tasks so shared shell scripts can be
maintained in one place and injected into Task runtime without relying on catalog-custom images.

Key points:

1. Move Task shared scripts from `images/scripts/` to `tasklib/scripts/`.
2. Author Task sources as `*.template.yaml` files.
3. Render runnable Task YAML with `gomplate` as a required developer step after Task changes.
4. Load shared scripts inside existing Task steps (no dedicated `load-scripts` step).
5. Commit rendered Task/Pipeline YAML together with template changes so review diffs clearly show
   impacted resources.
6. Enforce rendering consistency in `.tekton/images/all-in-one.yaml`; pipeline exits with error if
   render output is stale.
7. Enforce a minimal dependency contract for shared scripts: POSIX `sh` only, explicit CLI
   dependency declaration, and automated dependency verification.

The result keeps Task maintenance simple, supports official upstream tool images out of the box,
while preserving clear change visibility in pull requests.

## Motivation

Today several Tasks source shared scripts from `/usr/local/bin/*.sh`, where those files are copied
into custom images by `Containerfile`. This creates hard image coupling:

1. Users choosing official upstream images cannot reuse catalog shared scripts.
2. Users building their own images must repackage these scripts manually.
3. Shared script updates require image rebuild/release even for pure Task logic changes.

OpenShift demonstrates a valid generated-manifest pattern:

1. Rendered catalog artifacts in `p` branch are intended to be consumed directly (including Git
   Resolver workflows).
2. Their Tasks include script payload injection generated from templates.

References:

1. [OpenShift task-git rendered example (load script payload)](https://github.com/openshift-pipelines/tektoncd-catalog/blob/p/tasks/task-git/0.2.0/task-git.yaml#L213-L220)
2. [OpenShift catalog introduction (`main` for tooling, `p` for persisted consumable artifacts)](https://github.com/openshift-pipelines/tektoncd-catalog?tab=readme-ov-file#introduction)
3. [OpenShift template source (`load-scripts.tpl`)](https://github.com/openshift-pipelines/task-git/blob/main/templates/load-scripts.tpl)

Our scenario differs:

1. We do not require a dedicated persisted branch consumed directly via Git Resolver.
2. We still commit rendered Task YAML in the main workflow to make change impact explicit in code
   review and release auditing.
3. Rendering remains deterministic and verified by CI to avoid drift between templates and outputs.

### Goals

1. Decouple Task shared script delivery from catalog custom images.
2. Keep shared script source files maintainable and reusable across Tasks.
3. Ensure rendered Task/Pipeline YAML is updated and committed whenever templates change.
4. Auto-verify render consistency in required stages: integration testing and catalog packaging.
5. Avoid introducing a dedicated custom Go renderer.
6. Keep official tool images (for example `golang`, `node`, `dotnet`) usable in catalog Tasks.
7. Keep shared scripts portable by enforcing POSIX `sh` syntax and a minimal, declared CLI
   dependency set.

### Non-Goals {#non-goals}

1. Replacing all image-level runtime scripts in every image family.
2. Introducing a new Tekton API or controller for rendering.
3. Encrypting script payload in manifests.

### Use Cases {#use-cases}

1. A Task author updates `task-exec-lib.sh` once and dependent Tasks pick up the change after render.
2. A user runs catalog Tasks with official upstream images and still gets shared helper functions.
3. A reviewer can directly see in git diff which concrete Task YAML files are affected by a template
   or shared-script change.

### Requirements

1. Shared Task script source of truth must be outside image build context.
2. Rendering must be deterministic in local dev and CI.
3. Generated manifests must be self-contained for runtime (no external fetch).
4. Rendered manifests must be committed with source changes.
5. CI must fail when rendered manifests are out of date.
6. Shared scripts must use POSIX `sh` syntax only (no `bash`-specific features).
7. Shared script CLI/tool dependencies must be explicitly documented in `tasklib/scripts/README.md`.
8. Changes introducing new dependencies must be automatically detected and blocked unless declared.
9. Generated Task file naming must stay compatible with current layout (for example,
   `task/python/0.1/python.yaml`).

## Proposal

Adopt template-driven rendering with inline shared-script bootstrap in existing steps.

1. Move shared Task scripts from `images/scripts/` to `tasklib/scripts/`.
2. Adopt `*.template.yaml` naming for render sources.
3. Use `gomplate` for rendering; read script files directly in templates with `file.Read`, then
   encode with `base64.Encode`.
4. In each step that needs shared libs, inline a bootstrap snippet that writes scripts into
   `/scripts` (`emptyDir` + `volumeMount`) and then `source` them.
5. Render output stays in existing Task/Pipeline directories (for example `task/*/*/<name>.yaml`)
   to keep current test and packaging inputs unchanged.
6. Developers must run the render target after Task/template changes and commit rendered files.
7. Add a strict verification target (for example `verify-rendered-tasks`) and run it in
   `.tekton/images/all-in-one.yaml`; if render output differs from git state, fail fast.
8. Define shared-script dependency contract:
   1. POSIX `sh` syntax only.
   2. Dependencies declared in `tasklib/scripts/README.md`.
   3. Automated checks for syntax and undeclared commands.
9. Add a minimal-dependency script contract test image in CI to prevent implicit dependency growth.
10. The same mechanism can be reused later for other cross-Task shared scripts or shared resources
   (for example common snippets, static payload files), not only current shell libs.

### Notes and Caveats {#notes-and-caveats}

1. `base64` is used for transport fidelity and escaping stability, not for security.
2. Manifest size increases due embedded script payloads.
3. During migration, template-based and legacy static Tasks can coexist.
4. Committing rendered outputs increases diff size, but this is intentional to improve review
   visibility and release traceability.

## Design Details {#design-details}

### Directory Layout

```text
catalog/
  tasklib/
    scripts/
      README.md
      load_env_config.sh
      task-exec-lib.sh
      task-runtime-lib.sh
      scm-prepare-context.sh
      scm-setup-runtime.sh
      tests/
  task/
    golang/0.1/golang.template.yaml
    nodejs/0.1/nodejs.template.yaml
  pipeline/
    xxx/0.1/xxx.template.yaml
```

Guideline:

1. `tasklib/scripts/`: reusable shared Task libs.
2. `images/**/scripts/`: scripts required by image entrypoint/runtime only.

### Template Example (`*.template.yaml`)

The template below shows script bootstrap inside an existing step, not a separate load step.

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: golang
spec:
  volumes:
    - name: shared-scripts
      emptyDir: {}
  steps:
    - name: run
      image: $(params.image)
      script: |
        #!/usr/bin/env sh
        set -eu

        mkdir -p /scripts
        if [ ! -f /scripts/.catalog-shared-ready ]; then
          printf '%s' '{{ file.Read "tasklib/scripts/task-exec-lib.sh" | base64.Encode }}' | base64 -d > /scripts/task-exec-lib.sh
          printf '%s' '{{ file.Read "tasklib/scripts/load_env_config.sh" | base64.Encode }}' | base64 -d > /scripts/load_env_config.sh
          chmod 0755 /scripts/*.sh
          touch /scripts/.catalog-shared-ready
        fi

        . /scripts/task-exec-lib.sh
        . /scripts/load_env_config.sh

        # task business logic...
      volumeMounts:
        - name: shared-scripts
          mountPath: /scripts
```

### Why `base64` is still needed

`base64` is retained even with template rendering because it improves robustness:

1. Preserves exact script bytes through YAML and shell quoting boundaries.
2. Avoids escaping issues around `$`, backticks, backslashes, and heredoc-sensitive content.
3. Produces deterministic payload strings for stable render output.
4. Keeps script materialization in a single-line pattern (`printf '%s' '<b64>' | base64 -d > ...`),
   reducing author cognitive load so they can focus on Task business logic instead of tool-helper
   plumbing, which is consistent with the current implementation style.

### Rendering Without a Custom Go Program

Use `gomplate` with a generic shell wrapper that does not require per-script environment variables.

Example render helper (`hack/render-task-templates.sh`):

```bash
#!/usr/bin/env bash
set -euo pipefail

# Resolve repository root.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Render one template file in place.
# Output name keeps compatibility with existing convention:
# task/<name>/<version>/<name>.yaml
render_one_template() {
  local src="$1"
  local version_dir
  local component_name
  local out

  version_dir="$(dirname "${src}")"
  component_name="$(basename "$(dirname "${version_dir}")")"
  out="${version_dir}/${component_name}.yaml"

  mkdir -p "$(dirname "${out}")"
  gomplate --file "${src}" --out "${out}"
  echo "rendered: ${out}"
}

while IFS= read -r -d '' src; do
  render_one_template "${src}"
done < <(find "${ROOT_DIR}/task" "${ROOT_DIR}/pipeline" -type f -name '*.template.yaml' -print0)
```

Because templates read script files directly via `file.Read`, adding a new shared script does not
require changing `render-task-templates.sh`.

### Integration Points

#### Local and CI integration tests

```makefile
.PHONY: render-task-templates
render-task-templates: gomplate
	./hack/render-task-templates.sh

.PHONY: verify-rendered-tasks
verify-rendered-tasks: render-task-templates
	@# Fail if tracked files changed after rendering.
	git diff --exit-code -- task pipeline
	@# Fail if rendering introduces untracked manifests.
	test -z "$$(git ls-files --others --exclude-standard -- task pipeline)"

integration-test: verify-rendered-tasks clean create-testing-ns
	go test -timeout 0 -v ./godogs $(GODOG_ARGS) --godog.tags="$(TAGS) && @automated && ~@automatable && ~@manual"
```

Integration tests keep using existing path conventions because rendered files are written in place.
`verify-rendered-tasks` makes render+commit mandatory before test and CI execution.

#### Catalog packaging flow (`all-in-one`)

At `.tekton/images/all-in-one.yaml` current `prepare-command` (around `2971-2974`), render first,
verify consistency, then copy rendered assets:

```yaml
- name: prepare-command
  value: |
    set -euo pipefail

    make verify-rendered-tasks || {
      echo "Rendered task/pipeline manifests are stale."
      echo "Please run: make render-task-templates and commit updated YAML files."
      exit 1
    }

    # copy rendered task and pipeline to catalog dir
    cp -rf ./task ./pipeline ./images/catalog/
```

Also include `tasklib/scripts/` and `*.template.yaml` in change detection inputs.

### Rendered YAML Commit Policy

Rendered Task/Pipeline YAML is part of the committed source of truth for review visibility.
Template updates are invalid unless matching rendered manifests are included in the same change set.

Policy:

1. Keep rendered outputs tracked in git.
2. Require `render-task-templates` before commit.
3. Block stale render output in CI (`verify-rendered-tasks`).

### Shared Script Minimal Dependency Contract

Shared scripts under `tasklib/scripts/` must follow a strict portability contract:

1. Syntax: POSIX `sh` only.
2. Shebang: use `#!/usr/bin/env sh` (or equivalent POSIX `sh` entry).
3. No `bash`-only features (for example arrays, `[[ ... ]]`, `${var//x/y}`, process substitution).
4. Every external CLI/tool dependency must be declared in `tasklib/scripts/README.md` before use.
5. New dependencies are not allowed without explicit contract update and review.

Recommended CI checks:

1. POSIX syntax/static checks:
   1. `shellcheck -s sh tasklib/scripts/*.sh`
   2. `checkbashisms tasklib/scripts/*.sh`
2. Dependency declaration check:
   1. Run `hack/verify-tasklib-script-deps.sh` to detect external commands used in scripts.
   2. Ensure detected commands are listed in README dependency section.
3. Minimal image contract test (runtime):
   1. Build/use a minimal verification image that contains only POSIX `sh` and declared
      dependencies.
   2. Execute script contract tests in this image; fail on `command not found` or syntax/runtime
      incompatibility.

This combined strategy (static + runtime contract image) is preferred over only integration tests,
because it catches dependency drift earlier and with lower cost.

### Avoiding function collisions and drift

Avoid direct copy-paste of shared function bodies into each business script.

1. Keep shared logic in `tasklib/scripts/*.sh`.
2. Bootstrap and source those files at runtime from `/scripts`.
3. Reuse common bootstrap snippets through template includes or documented copy pattern to keep
   behavior consistent.
4. Existing image-path sourcing patterns must be migrated accordingly. Example:
   replace `. /usr/local/bin/task-exec-lib.sh` with bootstrap + `. /scripts/task-exec-lib.sh`.

## Design Evaluation {#design-evaluation}

### Reusability

High. Shared shell libs are centralized and reused across Tasks.

### Simplicity

Moderate. Authors maintain plain shell files and template YAML; rendering stays CLI-based.

### Flexibility

High. Users can choose official or custom images without changing shared script delivery.

### Conformance

No Tekton API changes. Final outputs remain standard Tekton Task YAML.

### User Experience {#user-experience}

Task consumers get out-of-box compatibility with official images. Task authors and reviewers can
directly see impacted rendered Task/Pipeline YAML in pull requests.

### Performance

Rendering overhead is minimal. Runtime overhead is limited to a small bootstrap block in steps that
actually need shared libs.

### Risks and Mitigations {#risks-and-mitigations}

1. Risk: missing `gomplate` in local or CI.
   Mitigation: provide a pinned install target.
2. Risk: manifest size growth due embedded script payload.
   Mitigation: include only scripts needed by each Task.
3. Risk: migration complexity between static and template Tasks.
   Mitigation: migrate task-by-task and keep filename/layout compatibility (`<name>.yaml`) to avoid
   test and packaging path churn.
4. Risk: shared scripts accidentally introduce non-POSIX syntax or undeclared dependencies.
   Mitigation: enforce `shellcheck -s sh`, `checkbashisms`, dependency declaration checks, and
   minimal-image contract tests in CI.

### Drawbacks

1. Generated YAML is less human-readable than source templates.
2. Pull requests include additional rendered-YAML diffs, increasing review volume.

## Alternatives

### Alternative A: Dedicated custom Go renderer

Rejected. Extra binary lifecycle and maintenance are unnecessary for this scope.

### Alternative B: Kustomize patch-based script injection

Not selected as primary approach.

1. Multiline script payload patches are hard to maintain at scale.
2. File content ingestion/encoding is less direct than template functions.
3. Reusability across many Tasks is weaker than shared template helpers.

### Alternative C: Do not commit rendered YAML (on-demand only)

Rejected for our scenario.

1. It weakens review visibility because template changes do not directly show rendered impact.
2. It depends on every downstream flow re-rendering correctly, which reduces release traceability.

## Implementation Plan {#implementation-plan}

1. Create `tasklib/scripts/` and migrate shared Task libs from `images/scripts/`.
2. Introduce `*.template.yaml` for selected Tasks/Pipelines.
3. Add `gomplate` target and `hack/render-task-templates.sh`.
4. Render in place with filename convention compatibility (`task/<name>/<version>/<name>.yaml`).
5. Add `verify-rendered-tasks` and wire it into `.tekton/images/all-in-one.yaml` prepare phase.
6. Add shared script dependency contract checks (`sh` syntax + declared dependency verification).
7. Add minimal dependency verification image and script contract tests in CI.
8. Add developer documentation for this rendering mechanism and update relevant skills accordingly.

### Test Plan {#test-plan}

1. Run shared script unit tests from `tasklib/scripts/tests`.
2. Run render smoke test for all `*.template.yaml` files.
3. Run `verify-rendered-tasks` to ensure rendered YAML is up-to-date and committed.
4. Run POSIX compatibility checks for shared scripts (`shellcheck -s sh`, `checkbashisms`).
5. Run dependency declaration checks against `tasklib/scripts/README.md`.
6. Run shared script contract tests in the minimal dependency verification image.
7. Run existing integration suites against rendered manifests.
8. Verify packaging artifact contains rendered runnable YAML.

### Upgrade and Migration Strategy {#upgrade-and-migration-strategy}

1. Keep legacy static YAML runnable during migration.
2. Move Task-by-Task to `*.template.yaml` and rendered output consumption.
3. Remove obsolete image-coupled script references after migration completes.

## References

1. [OpenShift task-git rendered example](https://github.com/openshift-pipelines/tektoncd-catalog/blob/p/tasks/task-git/0.2.0/task-git.yaml#L213-L220)
2. [OpenShift catalog introduction](https://github.com/openshift-pipelines/tektoncd-catalog?tab=readme-ov-file#introduction)
3. [OpenShift `load-scripts.tpl` template](https://github.com/openshift-pipelines/task-git/blob/main/templates/load-scripts.tpl)
4. [gomplate file functions (`file.Read`, `file.ReadDir`, `file.Walk`)](https://docs.gomplate.ca/functions/file/)
5. [gomplate base64 functions (`base64.Encode`)](https://docs.gomplate.ca/functions/base64/)
