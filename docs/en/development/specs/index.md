# Development Specs

Internal development / design specs for tektoncd-operator changes (KEP + EARS style).
These are engineering design documents tied to a specific change or issue; they are **not**
part of the externally published product documentation.

Each spec is a single markdown file named `<topic>-<issue>.md`.

## Index

- [OLM upgrade blocked by tightened `required` CRD fields (DEVOPS-44435)](./olm-upgrade-required-fix-devops-44435.md)
  — make the 4.0.x → 4.13 OLM upgrade pass by stripping every `required` under the `spec` schema
  subtree of all `operator.tekton.dev` CRDs, plus CI guard and an oldest-baseline upgrade e2e.
