---
weight: 90
sourceSHA: 03ac2d42d2397a11201f97e92d9e17702c37dfd3dec9452ff0f442bb95e86d9d
---

# API List

## Endpoints

### `/v1/catalogs`

- **Method**: GET
- **Description**: Lists all Catalogs
- **Input**: None
- **Output**:
  - 200: OK response.
  - 500: internal-error: Internal Server Error
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/catalogs"
  ```

### `/v1/query`

- **Method**: GET
- **Description**: Searches for resources based on name, type, catalog, category, platform, and tag combinations
- **Input**:
  - name: Resource name
  - catalogs: Resource catalog
  - categories: Resource category
  - kinds: Resource type
  - tags: Resource tags
  - platforms: Resource platform
  - limit: Maximum number of resources to return
  - match: Matching strategy
- **Output**:
  - 200: OK response.
  - 400: invalid-kind: Invalid Resource Kind
  - 404: not-found: Resource Not Found Error
  - 500: internal-error: Internal Server Error
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/query?name=buildah&catalogs=tekton&categories=build&kinds=task&tags=image&platforms=linux/amd64&limit=10&match=contains"
  ```

### `/v1/resource/version/{versionID}`

- **Method**: GET
- **Description**: Finds a resource using the version ID
- **Input**:
  - versionID: Resource version ID
- **Output**:
  - 200: OK response.
  - 404: not-found: Resource Not Found Error
  - 500: internal-error: Internal Server Error
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/resource/version/1"
  ```

### `/v1/resource/{catalog}/{kind}/{name}`

- **Method**: GET
- **Description**: Finds a resource using the catalog name, resource name, and resource type
- **Input**:
  - pipelinesversion: Tekton pipelines version
  - catalog: Catalog name
  - kind: Resource type
  - name: Resource name
- **Output**:
  - 200: OK response.
  - 404: not-found: Resource Not Found Error
  - 500: internal-error: Internal Server Error
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/resource/tekton/task/buildah"
  ```

### `/v1/resource/{catalog}/{kind}/{name}/raw`

- **Method**: GET
- **Description**: Retrieves the latest resource YAML file
- **Input**:
  - catalog: Catalog name
  - kind: Resource type
  - name: Resource name
- **Output**:
  - 200: OK response.
  - 404: not-found: Resource Not Found Error
  - 500: internal-error: Internal Server Error
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/resource/tekton/task/buildah/raw"
  ```

### `/v1/resource/{catalog}/{kind}/{name}/{version}`

- **Method**: GET
- **Description**: Finds a resource using the catalog name, resource name, resource type, and version
- **Input**:
  - catalog: Catalog name
  - kind: Resource type
  - name: Resource name
  - version: Resource version
- **Output**:
  - 200: OK response.
  - 404: not-found: Resource Not Found Error
  - 500: internal-error: Internal Server Error
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/resource/tekton/task/buildah/0.1"
  ```

### `/v1/resource/{catalog}/{kind}/{name}/{version}/raw`

- **Method**: GET
- **Description**: Retrieves the YAML file of the specified version of the resource
- **Input**:
  - catalog: Catalog name
  - kind: Resource type
  - name: Resource name
  - version: Resource version
- **Output**:
  - 200: OK response.
  - 404: not-found: Resource Not Found Error
  - 500: internal-error: Internal Server Error
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/resource/tekton/task/buildah/0.1/raw"
  ```

### `/v1/resource/{catalog}/{kind}/{name}/{version}/readme`

- **Method**: GET
- **Description**: Retrieves the README of the specified version of the resource
- **Input**:
  - catalog: Catalog name
  - kind: Resource type
  - name: Resource name
  - version: Resource version
- **Output**:
  - 200: OK response.
  - 404: not-found: Resource Not Found Error
  - 500: internal-error: Internal Server Error
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/resource/tekton/task/buildah/0.1/readme"
  ```

### `/v1/resource/{catalog}/{kind}/{name}/{version}/yaml`

- **Method**: GET
- **Description**: Retrieves the YAML of the specified version of the resource
- **Input**:
  - catalog: Catalog name
  - kind: Resource type
  - name: Resource name
  - version: Resource version
- **Output**:
  - 200: OK response.
  - 404: not-found: Resource Not Found Error
  - 500: internal-error: Internal Server Error
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/resource/tekton/task/buildah/0.1/yaml"
  ```

### `/v1/resource/{id}`

- **Method**: GET
- **Description**: Finds a resource using the resource ID
- **Input**:
  - id: Resource ID
- **Output**:
  - 200: OK response.
  - 404: not-found: Resource Not Found Error
  - 500: internal-error: Internal Server Error
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/resource/1"
  ```

### `/v1/resource/{id}/versions`

- **Method**: GET
- **Description**: Finds all versions of a resource
- **Input**:
  - id: Resource ID
- **Output**:
  - 200: OK response.
  - 404: not-found: Resource Not Found Error
  - 500: internal-error: Internal Server Error
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/resource/1/versions"
  ```

### /v1/resources

- **Method**: GET
- **Description**: Lists all resources, sorted by score and name
- **Input**:
  - limit: Maximum number of resources to return
- **Output**:
  - 200: OK response.
  - 404: not-found: Resource Not Found Error
  - 500: internal-error: Internal Server Error
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/resources?limit=10"
  ```

### /v1/schema/swagger.json

- **Method**: GET
- **Description**: Downloads the JSON document of the API swagger definition
- **Input**: None
- **Output**:
  - 200: File downloaded
- **Example**:
  ```bash
  curl -X GET "https://api.hub.tekton.dev/v1/schema/swagger.json"
  ```
