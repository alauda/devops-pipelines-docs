---
title: Tech Design for Pipeline Orchestration and Execution with Connector Integration
---

# TEP-0005: Tech Design for Pipeline Orchestration and Execution with Connector Integration

## Summary

This tech design is a technical specification for the implementation of Pipeline Orchestration and Execution with Connector Integration.

## Proposal

### 基本思路

结合 [./0004_pipeline_connector_integration.md](./0004_pipeline_connector_integration.md)， 我们有两个概念要定义。

`Resource Interface` 和 `Integration` 概念。

`Resource Interface` 抽象了不同资源类型要满足的"接口/约束"，以便在 Pipeline 是引用对应的 实例化 Resource. 这里我们使用 `ResourceClass` 来表示这一抽象。

`Integration` 抽象了 Pipeline 编排过程中， 依赖的某个具体的资源的抽象。 例如具备某个特定 revision 的码仓库。 这里我们使用 `PipelineResource` 来表示这一抽象。

我们为不同的资源类型定义不同的 ResourceClass， ResourceClass 定义自己需要的表单，Pipeline 编排时，根据 ResourceClass 的定义，实例化对应的 PipelineResource。

一个 PipelineResource 通过引用一个 Connector 来表明当前资源的工具以及凭据信息。
现有的 ConnectorClass 声明自身支持的 ResourceClass，以便在创建 PipelineResource 时，可以列出满足要求的 Connector。

PipelineResource 创建时，自动根据当前 Resource 的配置信息，自动生成 Pipeline 参数 以及 Workspace 参数，并记录 Resource 属性和参数以及 Workspace 的关系。

Pipeline 编排过程中，根据 Task 的标记信息，推荐给用户合适的 Resource 属性值（例如 url,revision）。

同时，在编排或者触发时，选择资源时，通过参数关联的 PipelineResource 信息，请求对应 Connector 所提供的 API ，来提供获取/选择资源的能力。

**ConnectorClass**

声明支持的 ResourceClass。一个 ConnectorClass 可以支持多个 ResourceClass。

**ResourceClass**

为特定类型的资源， 定义数据结构约束以及行为约束。

例如

- `GitCodeRepository` ResourceClass 表示，需要引入一个 CodeBase 资源时， 如何创建 GitCodeRepository 资源，例如需要提供 Url 和 Revision 参数。
- `OCIArtifact` ResourceClass 表示，需要引入一个 OCIArtifact 资源时， 如何创建 OCIArtifact 资源，例如需要提供 Repository, Tag 参数。

**PipelineResource**

Pipeline 编排过程中, 依赖的某个具体的资源的抽象。 例如具备某个特定 revision 的码仓库。 资源的必备属性信息，由 ResourceClass 定义。

### ConnectorClass

ConnectorClass 声明支持的 ResourceClass。一个 ConnectorClass 可以标记支持多个 ResourceClass。

``` yaml
kind: ConnectorClass
metadata:
  name: git
  labels:
    resourceclass.connectors.cpaas.io/GitCodeRepository: "true"
spec: {}
---
kind: ConnectorClass
metadata:
  name: github
  annotations:
    resourceclass.connectors.cpaas.io/GithubCodeRepository: "true"
    resourceclass.connectors.cpaas.io/GithubOCIArtifactRepo: "true"
spec: {}
```

### ResourceClass

- ResourceClass 中约束创建 Resource 时所需要的参数
- 一个 ResourceClass 可以继承自某个 ConnectorClass， 也可以不继承。
- 参数和表单分离。 参数是用来约束创建 Resource 时所需要的参数，单独使用表单来描述，如何完成这些参数的输入。

``` yaml
kind: ResourceClass
metadata:
  name: GitCodeRepository
spec:
  extends: "" # 表示继承自哪个 ConnectorClass

  params: # Params 表示创建该 GitCodeRpository 类型的 Resource 时，必要的数据字段是什么
  - name: repository
    type: string # 支持 string, array, object
    parameterize:
      name: git-repository # 参数化时，默认的参数名称
  - name: revision
    type: string
    parameterize: # 参数化的含义: 如果用户勾选了参数化，则表示编排的 Pipeline 增加一个名为 git-revision 的时参数。
      name: git-revision

  # Output 表示该类型的 Resource，可以提供哪些信息给 Pipeline 编排时使用. 用户可根据需要来扩展 output 的定义
  # 分为 attributes, workspaces, apis 三个部分。
  output:
    attributes:
    - name: url
      value:
        # expression: $(connector.spec.address)/$(attributes.repository)
      type: string
    - name: revision
      value:
        attribute: revision # 引用 attribute 的值
      type: string
    workspaces: # 声明当前 resourceclass 可以实例化的 workspace list
    - name: git-source # 未提供任何信息，在创建 Resource 的时候， 确认是 pvcClaim 类型 还是 sc

    - name: git-basic-auth # 提供了部分初始化信息，在创建 Resource 的时候，workspace 表单使用这些默认值，用户可修改。
      parameterize:
        name: git-basic-auth
      csi:
        volumeAttributes:
          configuration.names: "gitconfig"
          token.expiration: 30m

    - name: git-ssh-auth
      parameterize:
        name: git-ssh-authth
      csi:
        volumeAttributes:
          configuration.names: "sshconfig"
          token.expiration: 30m

    apis: # 定义该 resource 的 api 接口的实现约定，表示如果实现了该 ResourceClass, 则实现了如下接口。
    - name: git-revision # 在其他地方，可以通过 name 来引用
      path: /api/v1/revisions?url=$(attributes.url)

status:
  output: # 最终计算出来的 output 信息
    attributes: # 根据 extends 信息，动态计算而来
    - name: url
    - name: revision
    workspaces: # 根据 extends 信息，动态计算而来
    - name: git-source
    - name: git-basic-auth
    apis:
    - name: git-revision
      path: /api/v1/revisions?url=$(attributes.url)
```


#### 扩展新类型

**定义新类型**

可以为不同的 Resource，定义不同的资源。例如

- GitCodeRepository
- OCIArtifact
- MavenArtifact

``` yaml
kind: Resource
metadata:
  name: OCIArtifact
spec:
  params:
  - name: repository
    type: string
  - name: tag
    type: string
```

这些 ResourceClass 我们需要内置到系统中，通过 api 提供给前端。

**通过继承扩展新类型**

考虑 Github, Gitlab 都可以提供 CodeRepository, 为保持底层 CodeRepository 抽象能力不变，使用 extends 来表示，自动继承来自某个 ResourceClass 的定义。
使用继承后，可以减少重复定义，并且在底层抽象新增能力后，上层可直接复用。

比如，在 GitCodeRepository ResourceClass 中，定义了新的 depth 参数，那么上层的 ResourceClass 中，也可以自动包含该参数。

如为 Github 定义独立的 GithubCodeRepository ResourceClass

``` yaml
kind: ResourceClass
metadata:
  name: GithubCodeRepository
spec:
  extends: GitCodeRepository

  params: {} # 为空时，继承 GitCodeRepository 的 params 定义

  output:
    attributes: {} # 为空时，继承 GitCodeRepository 的 output 定义
    workspaces: {} # 为空时，继承 GitCodeRepository 的 workspaces 定义
    apis: {} # 为空时，继承 GitCodeRepository 的 apis 定义
status:
  attributes: {} # 根据 extends 信息，动态计算而来
  workspaces: {} # 根据 extends 信息，动态计算而来
  apis: {} # 根据 extends 信息，动态计算而来
```

#### 表单定义

- 通过单独的定义来描述不同 params 的交互定义。 比如在 annotations 中保存 params.repository 的交互。
- 不同的工具，对于同一个 params 的交互定义可能是不同的, 可以在 对应的 ResourceClass 中进行定义。
  * 比如 gitcoderepository 的 repo 是输入的
  * 比如 githubcoderepository 的 repo 是下拉选择的, 先选择 org， 再选择 repo name。


**TODO**: 设计一套表单描述，来支持此场景。

``` yaml
annotations:
  x-descriptors:
```

### PipelineResource

用来实现 [./0004_pipeline_connector_integration.md](./0004_pipeline_connector_integration.md) 中定义的 `integration` 的概念。
该信息保存到 Pipeline 资源中， 并非实际的 k8s 资源。

该信息的数据结构由对应的 ResourceClass 做定义。

``` yaml
name: my-app-codebase
# 引用 ResourceClass 的版本
resourceClassRef:
  name: GitCodeRepository
  apiVersion: v1alpha1
connectorRef:
  name: "git-connector"
  namespace: "default"

params:
- name: repository
  value: "myorg/my-app-new"
  annotations:
    fieldsPath: | # 前端自行定义
      - tasks.clone.params.url
- name: revision
  param: git-revision # 表示对 revision 参数化，Pipeline 的 spec.params 中增加一个名为 git-revision 的参数。
  annotations:
    fieldsPath: | # 前端自行定义
      - tasks.clone.params.revision

workspaces: # 创建 Resource 时，将 class 中定义的 workspace 实例化，补充未填写的字段。
- name: git-source # 创建 Resource 时, 配置 source workspace 为使用已存在的 pvc
  persistentVolumeClaim:
    claimName: mypvc
- name: git-basic-auth
  csi:
    driver: connectors-csi
    readOnly: true
    volumeAttributes:
      connector.name: git-connector
      configuration.names: "gitconfig"
      token.expiration: 30m
```

#### PipelineResource 表单

**Type && ConnectorRef**

Type 可选择 ResourceClass ， ConnectorRef 对应相应实现了 ResourceClass 的 ConnectorClass 范围下的 Connector 类型。

**Params 表单**

- 使用选定的 ResourceClass 资源中的 Params 信息进行表单渲染。 表单的交互由对应的交互描述信息决定。

**Workspaces 表单**

- 选定的 Connector 所对应的 ResourceClass 中，定义了可选的 workspace 范围。 比如 git-basic-auth, git-ssh-auth, source.
- 添加特定 workspace 时，结合 ResourceClass 中的信息，渲染表单，填充默认值。

#### 流水线参数和 Resource 的参数映射

**Param**

标记参数化时

- Pipeline spec.params 增加 item

``` yaml
spec:
  params:
  - name: git-revision
    type: string
    value: ""
```

- resource.params 中配置如下信息， 同时前端记录 spec.params.git-revision 来自 resources[xx].params.revision。

``` yaml
params:
- name: revision
  param: git-revision
```

在执行触发时，
根据 resource.params.revision 的表单定义， 渲染 Revision 表单。选择具体的值之后，按照普通PipelineRun 的逻辑，传入param 的值。

**Workspaces**

标记添加为 workspace 时

- Pipeline spec.workspaces 增加 item

``` yaml
spec:
  workspaces:
  - name: git-source
```

- resource.workspaces 中配置如下信息， 同时前端记录 spec.workspaces.git-source 来自 resources[xx].workspaces.git-source。

``` yaml
workspaces:
- name: git-source
  volumeClaimTemplate: {} # 由用户的输入决定
- name: git-basic-auth
  # csi:
```
在执行触发时, 根据 spec.workspaces.git-source 值的来源，填充 Workspace 的值。

**编排 Task 时的引用**

编排时，Task 引用 Resource 的 output。 Resource的 output 由 ResourceClass 中定义的 output 信息计算而来。

计算逻辑考虑：

- 定义一套 前端可识别的表达式， 由前端来完成 output 的计算逻辑。
- 由后端提供高级 API 来计算 output 值， 每次 Resource 的值有变更时，调用该 API 来获取 output 值。

``` yaml
status:
  output:
    attributes:
    - name: url
      expression: $(connector.spec.address)/$(attributes.repository)
```

前端引用时:

- 记录 PipelineTask Params 的值来自 resources[xx].output.attributes['x']。
- 根据 resources[xx].output.attributes['x'] 的值类型，填充展示 PipelineTask Params 的值

### 表单中的资源选择

- ResourceClass 中，定义当前类型的 Resource 可使用的 API 列表.

``` yaml
status:
  apis:
  - name: git-revision
    path: /api/v1/revisions?url=$(attributes.url)
```

- 在 UI 表单定义区域，在表单中定义当前依赖的资源名称。

``` yaml
annotations:
  x-descriptors:
    - resourcesclass.gitcoderepository.apis.name: git-revision
```

前端根据二者信息，使用 connector 信息，调用 connector api 获取数据，并展示。

## 实现步骤

同 [./0004_pipeline_connector_integration.md](./0004_pipeline_connector_integration.md) 对于 Implementation Plan 的定义， 我们可以

**Phase 1: Foundation (Milestone 1)**

后端

- 定义 ResourceClass 和 PipelineResource 的数据结构
- 系统内置 GitCodeRepository, GithubCodeRepository 资源, 且状态符合预期。
- 提供 ResourceClass 的 API， 前端依据 ResourceClass 的 API 来渲染 Resource 表单， 能够完成 PipelineResource 的结构构造。
- 按照约定， 在 ResourceClass 上添加表单描述信息。

前端

- 定义表单描述 DSL 以支持 GitCodeRepository, GithubCodeRepository 涉及到的表单交互。
- 以 GitCodeRepository 为例， 在 Pipeline 编码中实现构建 PipelineResource 的能力。

**Phase 2: Core Interfaces (Milestone 2)**

后端

- 添加 PipelineResource 的验证能力
- 定义并添加 GitCodeRepository 涉及到的 API 描述 以及 API 能力， 以及 补充 git-revision 的字段(以及其他) UI 描述，提供资源选择能力。
- 定义并添加 git-releated Task 的 PipelineResource annotations， 使得 Pipeline 编排时，能够根据 PipelineResource 的 annotations 信息，推荐合适的 Task 的参数。

前端

- 以后端提供的 GitCodeRepository 以及改造过的 git-related Task 为基础， 实现使用了 GitCodeRepository 资源情况下的 Pipeline 编排和触发体验。
  * 验证
  * 编排时参数联动和参数推荐
  * 执行时，参数推荐和参数推荐(赋值)

**Phase 3: Extended Interfaces (Milestone 3)**

- 实现 Github ConnectorClass 以及 GithubCodeRepository ResourceClass ?
- MavenArtifact-> GithubCodeRepository , 验证继承场景下的逻辑

**Phase 4: More Extended Interfaces (Milestone 3)**