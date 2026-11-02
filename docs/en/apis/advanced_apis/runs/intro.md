---
weight: 10
---

# Introduction

This API lists, reads, watches, and deletes PipelineRuns and TaskRuns. Responses use `tekton.dev/v1` and can include archived runs. Objects are ordered by start time.

This is not the native Kubernetes API. `kubectl`, and create, update, cancel, and rerun requests, still use the apiserver. Endpoint details are on the [PipelineRun](./pipelineruns.mdx) and [TaskRun](./taskruns.mdx) pages.

## Access

Call the API through the platform gateway. The service path is the path after ingress rewrite.

| Entry | Path |
| --- | --- |
| Global gateway | `API_GATEWAY/tektoncd-enhancement/apis/v1alpha1/...` |
| Business cluster | `API_GATEWAY/clusters-rewrite/CLUSTER/tektoncd-enhancement/apis/v1alpha1/...` |
| In-cluster service | `/apis/v1alpha1/...` |

Send a Kubernetes bearer token. Each call authorizes `tekton.dev` `pipelineruns` or `taskruns` for the verb, namespace, and, when present, name.

Reading an archived object also requires `results.tekton.dev` `records` `list` or `get`. Deleting an archive requires `records` `delete` and `logs` `delete`. Removing an empty Result also requires `results` `delete`. Without that permission, the empty Result remains.

A list without `records` permission still returns live objects and sets the archive header to `forbidden`. A filtered list, or a continuation after that permission is removed, returns 403. Get reads the live object before checking Results. Watch without `records` permission forwards a live deletion as `DELETED`.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: tekton-runs-reader
rules:
  - apiGroups: ["tekton.dev"]
    resources: ["pipelineruns", "taskruns"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["results.tekton.dev"]
    resources: ["records"]
    verbs: ["get", "list"]
```

## Ordering

The sort key is `status.startTime`, otherwise `metadata.creationTimestamp`. A valid value is RFC3339 with `Z` or a numeric offset, truncated to UTC seconds. The same second is ordered by UID descending. A missing or invalid time sorts after every timed object.

A live object hides the archived object with the same name, even when the live object does not match the filter. Several archived objects with the same name contribute only the latest sort key.

An archived response copy sets `resource.loaded.from.tektonResults` to `true`. A live copy omits that key. Do not write the annotation back, and do not use the list `resourceVersion` to update an archived object.

## Query

These parameters follow the existing list client. The API does not add status, task reference, or UID filters.

| Parameter | Rule |
| --- | --- |
| `labelSelector` | Kubernetes label selector. Requirements are combined with AND. |
| `fieldSelector` | Only `metadata.name` and `metadata.namespace`, with `=`, `==`, or `!=`. |
| `keyword` | Case-sensitive literal fragment of `metadata.name`. Maximum length is 253. |
| `field` | Defaults to `metadata.name`. No other value is accepted. |
| `limit` | `0` or omitted requests a full server page. The default cap is 5000, and a positive value is capped there too. |
| `continue` | Opaque token. Send it back unchanged. |
| `resourceVersion` | The response value is the live list resourceVersion. It only continues a watch. |
| `resourceVersionMatch` | `Exact` returns 400. `sendInitialEvents=true` requires `NotOlderThan`. |
| `timeoutSeconds` | An explicit value is 1 to 60 seconds. A negative value or a value above 60 returns 400. |
| `source` | Defaults to `all`. `live` returns only live objects and does not read the archive. |
| `watch` | `true` or `1` selects a watch. `false` ignores `allowWatchBookmarks`. |

`continue` cannot be combined with `resourceVersion` or `resourceVersionMatch`. A continuation must keep the same namespace, resource, selectors, keyword, field, and source. `limit` may change. A mismatched token returns 400.

A non-zero `resourceVersion` without `continue` starts a new query. It does not replay an old page.

## Response

A successful list returns the resource list kind and full objects. The last page omits `continue`. An empty `continue` ends this query. It does not mean the history is empty, and a short page is not proof of the last page.

```json
{
  "apiVersion": "tekton.dev/v1",
  "kind": "PipelineRunList",
  "metadata": {
    "resourceVersion": "12345",
    "continue": "opaque-token"
  },
  "items": []
}
```

The next page contains objects older than the last returned sort key. The token remains valid after objects change and on another replica.

- A newer object created during paging appears on a new query, not on the next page.
- An unreturned object is skipped for this session if its start time becomes newer than the token.
- A returned object can appear again if its start time becomes older than the token.

## Archive state

List responses set `X-Tekton-Archive-State`. The gateway must forward and expose this header and `Warning`. A state other than `included` or `disabled` also sends `Warning: 299`.

| State | Meaning |
| --- | --- |
| `included` | Live and archived objects were merged. |
| `disabled` | Results is not installed. The list contains live objects. |
| `unavailable` | The archive could not be read. An unfiltered new list still returns live objects. |
| `forbidden` | The caller cannot read records. An unfiltered new list still returns live objects. |
| `invalid-data` | The archive page could not be decoded. An unfiltered new list still returns live objects. |
| `live-only` | The caller set `source=live`. |

An unfiltered new list does not fail when the archive is unavailable. A list with `keyword`, `labelSelector`, or `fieldSelector` does not fall back to live objects. Explicit `timeoutSeconds` expiry returns 504. The server safety cap or an archive failure returns 503. Missing permission returns 403.

A continuation that already included archived data returns 503 when the archive later fails. The original token is not rewritten. Drop that token and send a new `source=live` query before replacing the displayed rows.

List, get, and delete use a five-minute safety cap when `timeoutSeconds` is omitted or `0`. That expiry is 503, not 504. Only a caller-provided `timeoutSeconds` expiry is 504. Watch uses 30 seconds when `timeoutSeconds` is omitted.

A live collection that exceeds its configured limit returns 413. The default limit is 50,000 objects or 32 MiB. The default response limit is 16 MiB, and one archived object is limited to 4 MiB.

## Watch

Watch the collection URL with `watch=true`, starting from the live `resourceVersion` returned by list. The response is `application/json`, with one Kubernetes watch event per line. Event types remain `ADDED`, `MODIFIED`, `DELETED`, `BOOKMARK`, and `ERROR`.

The server rewrites events before forwarding them.

| Upstream event | Downstream event |
| --- | --- |
| `ADDED` | The live object. A different-UID archive with the same name is sent as `DELETED` first. |
| `MODIFIED` | The live object. The archive is not queried. |
| `DELETED` | `MODIFIED` with the archived object when that archive still matches the watch selector. `DELETED` when no archive remains or the archive does not match. No event until the lookup is confirmed. |
| `BOOKMARK` | Forwarded. |
| `ERROR` | Forwarded, including 410 from resourceVersion compression. |

If the archive lookup for an `ADDED` event fails, the live `ADDED` is still sent.

A unified delete waits until the archive is gone, then sends `DELETED`. It does not publish the stored rewrite as `MODIFIED`.

`keyword` is accepted so a list query can be reused. Watch does not filter events by keyword. `continue` and `limit` are rejected. `sendInitialEvents=true` requires `resourceVersionMatch=NotOlderThan` and does not include archived objects. Archive failure does not close the stream and is not reported as 410.

The object `resourceVersion` on a rewritten event is the live event resourceVersion, not the value stored in the archive.

```json
{"type": "MODIFIED", "object": {"apiVersion": "tekton.dev/v1", "kind": "PipelineRun"}}
```

## Get and delete

Get authorizes the name and reads Kubernetes first. Only a live 404 reads the latest archive. `resourceVersion=0` is a current read and falls back like an omitted value. Any other non-empty `resourceVersion` is forwarded only to that live read. Both confirmed missing returns 404. Archive unavailable returns 503. Archive forbidden returns 403.

Delete removes the live object and the same-name archive. A UID precondition in the body is ignored. `gracePeriodSeconds`, `propagationPolicy`, and `dryRun` apply to the live object. Invalid DeleteOptions, including an invalid `dryRun`, are rejected before any archive or live change. An explicit dry-run does not read the Results configuration and does not delete the archive. If the archive cannot be queried, delete returns 503 and the live object remains. Retry the same name. A parent name does not delete child runs.

## Errors

Failures use a Kubernetes `Status` body.

| Condition | Result |
| --- | --- |
| Invalid credentials | 401 |
| Missing permission | 403 |
| Invalid parameter, name, or continue token | 400 |
| Both sources confirm the object is missing | 404 |
| Live delete conflict | 409 |
| Unsupported method | 405 |
| Live collection or response exceeds its limit | 413 |
| Caller `timeoutSeconds` expired | 504 |
| Server safety cap expired, or delete cannot read the archive | 503 |

POST, PUT, PATCH, and collection DELETE are not supported.
