---
created: '2025-01-10'
sourceSHA: 423aae74086ccd5e58bf95963dba1872dde2b1e215377c15812fd75e0246284b
---

# Update Frontend Images

## Background

The Tekton-Operator plugin not only includes community components, but also our platform's frontend images which provide UI capabilities.

Frontend components must be associated with the `Tekton-Operator` plugin to be used correctly by users.

Therefore, it's essential to explain how to submit tests and update frontend components.

## Main Branch (`main`, `release-*`)

Currently, the pipeline in the frontend component [pipeline-v2-frontend](https://github.com/AlaudaDevops/pipeline-v2-frontend) is configured so that when the latest frontend image artifacts are built in the main branch (`main`, `release-*`), they will be automatically updated in the `values.yaml` configuration file of the `Tekton-Operator`.

This update operation will also automatically trigger the `Tekton Operator Bundle` pipeline to build the latest `bundle` image. The `bundle` artifact will carry the latest frontend image upon deployment.

The `bundle` artifact built from the main branch will also be automatically updated in the corresponding branch of the [devops-artifact](https://github.com/AlaudaDevops/devops-artifact) repository in its [`values.yaml`](https://github.com/AlaudaDevops/devops-artifact/blob/main/values.yaml).

For example, the latest version here is `v0.0.1-alpha.53`
![](./assets/values-yaml.png)

## PR Branch

If the frontend component's PR branch artifacts are also expected to generate a temporary `bundle` artifact with the latest `Tekton-Operator` plugin for testing, it currently requires manually triggering the pipeline that builds the `bundle` artifact in the `Tekton-Operator`.

The specific steps are as follows:

- 1. Obtain the latest Tag of the frontend artifacts, for example, `v1.0.0-rc.1`

- 2. Find the latest `commit` in the [`Tekton Operator`](https://github.com/AlaudaDevops/tektoncd-operator) related branch
  - If the frontend PR is initiated against the target branch `main`, then the latest commit of the `main` branch needs to be found. Similarly, if it is a PR against `release-*`, the latest commit of the `release-*` branch must be located.
  - ![](./assets/find-last-commit.png)

- 3. In the `commit` comment, add a comment like the following to trigger the `bundle` artifact pipeline:

  ![](./assets/commit-comment.png)

  ```shell
  /test to-all-in-one branch:main overwrite_artifacts=".global.images.ui.tag=v1.0.0-rc.1"
  ```

  Where:

  - `/test` is the command prefix for `pac`
  - `to-build-bundle-image` is the name of the `PipelineRun` pipeline
  - `branch:main` is the executing branch of the pipeline
    - If the default branch is `main`, this can be omitted
    - If it is a `release-*` branch, it must be specified here
  - `overwrite_artifacts` is an execution parameter for `pac`, which can influence the execution parameters in the `PipelineRun`.
  - `".global.images.ui.tag=v1.0.0-rc.1"` is the parameter value for `overwrite_artifacts`.
    - `.global.images.ui.tag` is the `key` for the frontend image in `values.yaml`
    - `v1.0.0-rc.1` is the tag of the latest frontend artifact to be replaced

- 4. Check the execution status of the pipeline in the [`Tekton-Dashboard`](https://tekton-dashboard-edge.alauda.cn/#/namespaces/devops/pipelineruns) and wait for it to finish.
  - Pay attention to the `modify-values-yaml` Task in the execution phase of the pipeline, to see if the Tag of the frontend image in `values.yaml` is correctly updated.

    ![](./assets/pr-modify-values-yaml.png)

  - Obtain the image Tag of the built `bundle` artifact from the results of `build-image`.

    ![](./assets/pr-build-image.png)

    The artifact here is: `v0.0.1-alpha.53-250110072255`, where the latter part is a timestamp.
