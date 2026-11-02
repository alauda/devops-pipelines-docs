---
weight: 12
status: proposed
title: Unified live and archived Run access
creation-date: "2026-10-26"
category: docs
authors:
  - "@lfyou"
---

## Summary {#summary}

[DEVOPS-44553][issue] (related [DEVOPS-44552][related-issue]) adds a Run API
that stays close to native Kubernetes. List returns complete live and archived
PipelineRuns and TaskRuns, ordered by time. Get and Delete recognize both
sources. Watch reuses the live event stream and rewrites each event before
forwarding it.

**Results returns one ordered archive page from an expression index and a
keyset. enhancement reads the current live objects, orders them with the same
key, and merges them with the archive. `continue` stores only the query
fingerprint and the last position. When Results is unavailable, List still
returns live objects and says the archive is not included. The frontend adds a
thin Run service. The shared `K8sApiService` and `K8SResourceList` stay
unchanged.**

```text
frontend -> existing Gateway / enhancement authorization
         -> read and sort the current namespace live set
         -> Results reads one keyset page after the cursor
         -> merge, with a same-name live object winning
         -> Run List + continue
```

Status: proposed. The companion implementation is under review and is not
merged. [enhancement MR !65][implementation-draft] is that implementation, not
a finished release.

## Motivation {#motivation}

The frontend currently reads Kubernetes and Results separately and merges the
pages in the client. Neither source orders by the Run time used here. Taking
the first page from each source and merging them does not produce the newest
page.

Archive ordering, filtering, and pagination stay in the Results database.
enhancement orders only the current live set and merges it with the ordered
archive stream. The archive read uses the index and stops at the current page.

### Goals {#goals}

- Return a complete `PipelineRunList` or `TaskRunList`. Within one namespace
  and kind, the identity is `metadata.name`. A live object wins. Same-name
  archives return only the latest object.
- The first page and later pages use the same order. Reuse the existing name
  search and label filters. Status filtering stays in the frontend.
- List, Get, Delete, and Watch follow native parameters, responses, and
  permissions as closely as this API can. The frontend does not understand the
  Results protocol and does not keep two pagers.
- A Results failure, an index that is not ready, or an archive timeout must
  not block a live read. The response must say the archive is missing. It must
  not present a live list as complete history.
- Reuse the existing frontend, routing, deployment, and offline delivery.
  Maintain one implementation.

### Non-goals {#non-goals}

Do not change Tekton CRDs, etcd, or the archive and pruner sequence. Do not
register an APIService or replace the native Tekton routes. Do not aggregate
across clusters or all namespaces, add a log API, add a Watch event type, or
subscribe to a Results change stream. This feature is maintained internally
and is not contributed upstream.

Do not add a column to `records`, backfill rows, or add a table.

## Design details {#design-details}

### 1. API contract {#public-api}

```text
GET    /apis/v1alpha1/namespaces/{namespace}/pipelineruns
GET    /apis/v1alpha1/namespaces/{namespace}/taskruns
GET    /apis/v1alpha1/namespaces/{namespace}/{pipelineruns|taskruns}/{name}
DELETE /apis/v1alpha1/namespaces/{namespace}/{pipelineruns|taskruns}/{name}
GET    /apis/v1alpha1/namespaces/{namespace}/{pipelineruns|taskruns}?watch=true
```

The path version belongs to enhancement. Returned objects are `tekton.dev/v1`.
Namespace is validated as a Kubernetes name. Empty, `-`, and path injection
are rejected.

| Parameter | Contract |
| --- | --- |
| `labelSelector` | Kubernetes parser, including set-based selectors. Conditions are AND. |
| `fieldSelector` | Only `metadata.name` and `metadata.namespace`. Supports `=`, `==`, and `!=`. |
| `keyword` / `field` | The existing K8sApiService name search. `field` defaults to and only accepts `metadata.name`. No alias is added. |
| `source` | Defaults to `all`. `live` is only for the Run service to rebuild the live list after an archive failure. It is not a user filter. |
| `limit` | `0` or omitted returns everything that fits the capacity limits. A positive value returns at most N. The server page is at most 5000, and the byte budget may return a shorter page. |
| `continue` | The client sends the token back unchanged. The server token does not expose the Results page token. |
| `resourceVersion` | The response value is the Kubernetes resourceVersion of this live List. It is only used to continue Watch. |
| `resourceVersionMatch` | `Exact` returns 400. `sendInitialEvents=true` requires `NotOlderThan` and is forwarded to the apiserver. |
| `timeoutSeconds` | An explicit value is at most 60 seconds and expiry returns 504. A negative value or a value above 60 returns 400. List, Get, and Delete use a five-minute server safety cap when the value is omitted or `0`; expiry returns 503, not Gateway Timeout. An invalid value is not silently reduced to 30 or 60. Watch stays at 30 seconds when omitted. The cluster Ingress read and write idle timeout is 360 seconds, longer than this cap. |
| watch parameters | `watch=false` ignores `allowWatchBookmarks`. `watch=true` is defined in section 7. A non-watch `sendInitialEvents` is rejected by the native rule. |

Standard parameters reuse the `metav1.ListOptions` ParameterCodec and
`ValidateListOptions`. `keyword` and `field` are platform compatibility
parameters. Matching is literal and case-sensitive. They are not rewritten as
an exact fieldSelector. Do not add `taskRef`, `runStatus`, `uid`, or
`nameContains`. Task association continues to use `labelSelector`. Hub
reference, version, and status filtering stay in the frontend and do not apply
to pages that have not been loaded.

`continue` combined with a non-zero `resourceVersion` or
`resourceVersionMatch` returns 400. A non-zero resourceVersion without
`continue` does not replay an old page. It starts a new current query. A
continuation must keep the namespace, resource, filters, and order. `limit`
may change.

```json
{
  "apiVersion": "tekton.dev/v1",
  "kind": "PipelineRunList",
  "metadata": {
    "resourceVersion": "<live-list-rv>",
    "continue": "<opaque-token>"
  },
  "items": []
}
```

The response contains complete objects. An empty result is `items: []`. The
last page omits `continue`. The end of the range is `continue` being empty,
not `items.length < limit`. Do not add `total`, `source`, or
`remainingItemCount`. An archived response copy sets
`resource.loaded.from.tektonResults=true`. A live copy removes that key. The
annotation is not written back to the cluster and is not used for
authorization.

`metadata.resourceVersion` may differ between pages. It only continues the
live Watch. An archived object must not be written back to the native API with
the response resourceVersion. An ordinary `kubectl get` still uses the native
API.

### 2. Routing and authorization {#security}

Reuse the existing entry. The Gateway selects the cluster. Ingress strips the
service prefix:

| Entry | Path |
| --- | --- |
| global | `<API_GATEWAY>/tektoncd-enhancement/apis/v1alpha1/...` |
| business cluster | `<API_GATEWAY>/clusters-rewrite/{cluster}/tektoncd-enhancement/apis/v1alpha1/...` |
| Service or Pod | `/apis/v1alpha1/...` |

enhancement uses its own cluster configuration. It does not parse the cluster
or bypass the Gateway to reach Results. Both Gateway paths must be tested.

Every List, continuation, Get, Delete, and Watch calls
`requestauth.Authenticator.AuthenticateAndAuthorize` with `tekton.dev`, the
resource, namespace, verb, and name when required. Do not authenticate first
and then authorize again.

The caller permission is separate from the Results service account. A service
account that can read Results does not mean the caller can read the archive.
Archive list, get, and delete each check the matching verb on
`results.tekton.dev/records`. Deleting logs also requires `logs.delete`.
Deleting an empty Result container also requires `results.delete`; without it,
the empty container remains. Permissions are checked before any delete side
effect. Reading Records for the current page is an internal List step and does
not require the caller to get each item. The internal lookup for Get does not
require list. The internal lookup for Delete does not additionally require
get or list.

A live Get does not check Results first. Watch `ADDED` and `MODIFIED` do not
wait for Results. A List without archive permission returns the live list and
marks the state. Delete events for that caller are forwarded as live-only
`DELETED`. If archive permission is revoked on a continuation, return 403.
Do not append the remaining archive to the original page.

#### Caller identity for this delete {#delete-identity}

The native Delete must make the apiserver run authorization and admission as
the original caller's `user.Info`. Create a request-scoped client with
`rest.CopyConfig`, authenticate it as the dedicated service account, and set
`Impersonate.UserName`, `UID`, `Groups`, and `Extra`. Do not change the shared
client, do not forward an Impersonate header supplied by the caller, and do
not fall back to the service account identity. The identity is not stored. It
is discarded when the request ends.

| Source | Identity used for this request |
| --- | --- |
| Kubernetes | username, UID, groups, and extra from TokenReview in the target cluster |
| Platform | UserInfo from the existing platform route's SelfSubjectReview in the target cluster. It must be the identity that a native DELETE on the same route presents to admission. |
| OIDC | Username and group mapping from verified claims. The shared package does not create UID or extra, and `sub` is not used as UID. If the mapping is insufficient, reject this unified delete. |

If the identity required by admission cannot be expressed, fail before
deleting. On timeout or failure, the caller authenticates again and retries by
name. The Operator grants the dedicated identity `impersonate`. RBAC
impersonate cannot be limited by the later Run verb. The configuration and
identity mapping must be reviewed together. Missing permission does not affect
live Get, List, or Watch.

Whether an old archive remains visible after a same-name namespace is recreated
follows the existing tenant, retention, and cleanup mechanisms. If those
mechanisms do not prove isolation, confirm it separately before release.

Results uses an independent REST config and the existing token rotation.
Validate CA, ServerName, and audience. Do not skip TLS. The address comes only
from deployment configuration. Errors, logs, and metrics do not record
credentials, complete resources, or internal addresses.

### 3. Kubernetes source {#kubernetes-source}

Each page reads the **current** live set in the namespace. Kubernetes List
pages by name and cannot order by `startTime`, so the time merge must see the
current live set. The live count is normally much smaller than the archive.
This is one namespace List, not an archive table scan.

Reuse the dynamic client and page by 500. Object count and response bytes
accumulate in the same collection. Either limit returns 413 immediately and
does not request the next page. Save this List resourceVersion, put it in the
response, and use it to continue Watch. Also build the current live name set:
if a same-name live object exists now, hide the same-name archive even when
that live object does not match the filter.

Do not add an informer or a cache service. The cost of listing again on each
page is limited to the current live set. If measurement later shows this is
the bottleneck, reuse a cache that exists then. This change does not depend
on a cache for correctness.

The byte limit is applied before decoding. Create a dedicated client with
`rest.CopyConfig` and `Config.Wrap`. Pages share one byte counter. Crossing
the limit closes the current response and returns 413. Do not change the
controller client or the shared capabilities client. If the whole live set
still does not fit, return 413. If the internal Kubernetes continue expires,
collect once more within the same request deadline. A second failure returns
503 or 504. It is not disguised as an expired client continue.
### 4. Results index and ordered reads {#results-projection}

Archive ordering is done in PostgreSQL. For example, archives C(12:00),
B(10:00), and A(08:00), with live D(11:00) and `limit=2`, merge returns C and
D and then stops.

Do not change `records` columns and do not backfill rows. The sort value is
computed from JSON by an immutable function. The rule matches live objects:
`status.startTime` first, otherwise `metadata.creationTimestamp`. Accept only
RFC3339 with `Z` or a numeric offset, truncated to UTC seconds. The same
second is ordered by Run UID descending, `COLLATE "C"`.

`tekton_run_has_sort_time` and `tekton_run_sort_epoch` neither raise nor
return NULL for any input. A valid time returns `1` and the UTC seconds. A
missing or invalid time returns `0` and seconds `0`. PostgreSQL
`ORDER BY ... DESC` defaults to `NULLS FIRST`, so NULL would sort a missing
time first. A function error would make `CREATE INDEX` fail. The Go comparator
uses the same rule, truncates to seconds, and does not keep nanoseconds.
Both functions swallow conversion errors with `EXCEPTION`. `EXCEPTION` starts
a subtransaction and cannot run in a parallel query, so the functions must be
`PARALLEL UNSAFE`, not `PARALLEL SAFE` or `PARALLEL RESTRICTED`. The ordered
query sets `max_parallel_workers_per_gather` to 0 for its transaction before
running. The function result does not change, so existing indexes are not
rebuilt for that reason. Fractional seconds are removed before conversion to
`timestamptz`, so PostgreSQL does not round them. Do not use `btrim`.
Whitespace on either side is not a valid time. enhancement and Results each
keep this rule. They do not share a module. The query expression, `DESC`, and
`COLLATE "C"` must match the index definition literally.

```sql
CREATE INDEX CONCURRENTLY records_run_order ON records (
  parent,
  (data->>'kind'),
  (tekton_run_has_sort_time(data)) DESC,
  (tekton_run_sort_epoch(data)) DESC,
  ((data->'metadata'->>'uid')) COLLATE "C" DESC
);

CREATE INDEX CONCURRENTLY records_run_name ON records (
  parent,
  (data->>'kind'),
  (data->'metadata'->>'name'),
  (tekton_run_has_sort_time(data)) DESC,
  (tekton_run_sort_epoch(data)) DESC,
  ((data->'metadata'->>'uid')) COLLATE "C" DESC
);
```

`data->>'kind'` unifies v1 and v1beta1. The name index selects the latest
same-name row. Get, Delete, and Watch `DELETED` share that lookup. The lookup
uses only namespace, kind, and name. `parent` is that namespace, kind is
`data->>'kind'`, and the name is `data->'metadata'->>'name'`. When several
rows share a name, `NOT EXISTS` on that index selects the latest sort key,
then reads the complete Record. The query uses `metadata.name` and
`metadata.uid`. `records.name` is only the Results storage key and usually
equals the Run UID. A difference is not an identity conflict. List, Get, and
Delete use the name and UID inside the object. A newer row that lacks a name
or UID must not hide an older displayable row with the same name. The five
0011 indexes remain. They do not provide this time order. The query must call
the same functions and must not parse time with a second SQL implementation.

If the order index is missing or `indisvalid=false`, the new ordered query is
unavailable. A new List without filters returns the current live set and marks
the archive unavailable. It does not return 500 and does not fall back to an
unbounded full-table sort. Delete does not use this degradation. After the
index is valid, a sequential scan of a small table returns the archive if it
finishes within the timeout. A large unfiltered list relies on a query
expression that matches the index and a 2-second archive limit. Timeout is
treated as archive unavailable.

`keyword`, `labelSelector`, and `fieldSelector` are user searches or filters
and do not use those 2 seconds. They use the request deadline. An explicit
`timeoutSeconds` is at most 60 seconds and expiry returns 504. When omitted,
the deadline is the five-minute server safety cap, not 30 seconds. Crossing it
returns 503. The server must not describe its own deadline as Gateway Timeout.
A search that does not finish within the short limit must not mark the whole
history unavailable and must not return only live objects as the search
result. A completed search returns archive hits. An archive failure, an order
index that is not ready, or a page that cannot be parsed returns 503. No
permission returns 403. Results must return 403 when an authenticated caller
is denied. Historically it wrote the same denial as HTTP 401 with a permission
denied body. The unified API still treats that as 403 and must not show it as
an unavailable historical range. An invalid or missing credential remains 401.
A successful Result or Record read does not mean the archived log succeeded.
If log storage deletion fails, Delete returns 503 and the live object stays.

Name containment uses an escaped LIKE literal. For three or more characters
and no label, field, or name filter, first read a window after the cursor only
to choose a plan. If the distinct names in that window already fill a page,
fill the current page from that cursor on the time index and stop. Otherwise
use `records_run_name_trgm` to collect the hits and then sort them. That
window is not the result. For three or more characters plus an equality on
`tekton.dev/pipeline`, read the same window on that pipeline index. If the
probe or page plan would sort the whole range, use a bitmap, or use the global
time index, do not execute that SQL. If the window fills a page and the plan
is an Index Scan of `records_run_pipeline`, with the pipeline equality and
cursor in Index Cond, the keyword stays a filter and the page stops.
Otherwise sort only the intersection of that pipeline and the name. Do not
switch to the global time index. Other equality labels, with or without a
keyword of three or more characters, also read a window first. If a pipeline
equality is also present, read `records_run_pipeline`; otherwise read
`records_run_order`. If the window fills a page, the label and keyword stay
filters and the page stops on that index. Otherwise sort the hits with
`records_run_labels`. Do not add an index. One or two characters, field, name,
and inequality labels stay on their existing paths. A single character with no
other selective filter disables bitmap, sequential scan, and explicit sort for
the transaction and fills the page from `records_run_order`. When a label,
field, or name filter is also present, do not force that time index. Filling
the page would otherwise scan the whole time order. Equality on
`tekton.dev/pipeline` is the exception because its own ordered index can stop.
Disabling only bitmap and sequential scan makes PostgreSQL 12 use
`records_run_pipeline` and then sort, so LIMIT does not stop. A two-character
probe includes the same request's label, field, and name. If the fragment
alone fills a page but those conditions do not, do not force the time index.
Fill the page and stop on the time index only when the probe fills it.
Otherwise collect hits with `records_run_name_bigram` and sort them.
enhancement asks Results for `limit+1` archive rows, not more than the scan
budget. `limit=0` has no first-page promise, but a one- or two-character
search must not request a whole scan budget in one call. Do not treat a fixed
row-count time window as the query result, and do not sort every hit of a
common two-character fragment. Equality on `tekton.dev/pipeline` with no
keyword does not enter candidate scanning and does not probe first. It stops
when `records_run_pipeline` fills a page. If that index is not ready, the same
equality can still stop on `records_run_order`. A search index that is not
ready does not reject the query. The request deadline is the limit. After
candidate scanning, `NOT EXISTS` still applies to every same-name row. A newer
same-name row hides the older row even when the newer row does not match the
filter.

Index creation happens only when that index is first added, when a failed
build is repaired, or when the sort function changes and the index is rebuilt.
Results startup does not wait for `CREATE INDEX CONCURRENTLY`. Ordinary List,
Get, Delete, and Watch do not trigger index creation.

The current same-name Record keeps only the latest sort key. The same key is
then decided by Run UID and Record ID. Use the name index and `NOT EXISTS`.
Do not `DISTINCT ON` the whole namespace first, and do not filter first and
then choose the latest. Do not compare Record insertion time.

Filters use parent, kind, name, and label expressions, through the restricted
mapping of the CEL parser. enhancement builds the condition from validated
parameters. It does not accept caller CEL. `keyword` is an escaped literal
match. A low-hit filter may scan more index entries than one page. Returning
on demand does not mean every SQL statement reads only one page.

The existing ListRecords gains the product order
`order_by=run_start_time desc`. The page token stores the sort key. A public
continuation uses the row comparison `(has, epoch, uid) < cursor`, in the same
order as `records_run_order`, as an index condition that seeks from the
cursor. An expanded three-part OR is only a filter. A deep cursor would scan
from the newest row. A page without candidate scanning disables hash join and
merge join for the transaction, so `NOT EXISTS` stays a nested loop that can
stop. A page with candidate scanning also disables those joins and pages by
the hits' own sort keys. It does not probe candidates from the time index one
row at a time. Do not add a column or change the index direction. The old
create, update, and ID orders and their tokens keep their old behavior. The
current page returns complete Records directly.

### 5. Merge {#ordering}

The order is fixed: keep the latest same-name object, let live win, then
filter, then merge by sort key. If the same-name live object is `env=prod`
and the archive is `env=test`, a query for `env=test` must not return the old
archive.

| Case | Handling |
| --- | --- |
| Same-name live and archive | Return the current live object and hide the same-name archive. |
| Several same-name archives | Return only the current Record with the latest sort key. |
| `records.name` differs from `metadata.uid` | Not a conflict. Return the object as stored. Delete finds the log by the object UID. |
| One row cannot be shown: not an object, missing name or UID, wrong type or namespace, too large, or cannot be converted | Skip that row and move past it. Do not degrade the rest of the archive to invalid-data. Read at most 8 more times to pass a prefix that cannot be shown. Rows already read are returned. If no displayable row was read, the query fails closed and does not spin. |
| Query failure, or the whole page response cannot be parsed | A new List without filters returns live and marks the reason. A request with keyword, labelSelector, or fieldSelector does not degrade. One bad record does not use this degradation. |

Live and SQL use the same comparison rule and fixtures. Do not replace Run
time with Results create or update time, `summary.start_time`, or Record ID.

The public continue token is base64url JSON signed with the enhancement shared
key:

```json
{"v":1,"q":"<query-hash>","k":[1,1792886400,"<last-run-uid>"],"a":[1,1792886300,"<archive-uid>"]}
```

`q` binds namespace, resource, labelSelector, fieldSelector, keyword, and
source. `k` is the sort key of the last returned object. The next page takes
only older sort keys. An object newer than continue does not enter the current
pagination. A `source` that does not match continue returns 400, including a
mixed continue with `source=live`. `a` is used only when this page scanned
ahead in the archive to skip names hidden by live objects. The next page
continues there, so the same hidden rows are not scanned again. Without that
skip, `a` equals `k`. When the scan budget is exhausted and the archive is not
confirmed finished, stop the page and advance `a` to the last scanned archive
key. That is not archive completion. Do not return an older live object that
has not been compared. A short page is allowed. When the archive has been read
to the end, the same page continues to return older live objects.

The token does not authorize. A signature, query, or identity mismatch returns
400. Any enhancement replica can interpret the token.

### 6. Changes during pagination {#pagination}

Each page reads the live and archive state at the position in continue.
continue remains valid after creates, updates, deletes, and replica changes.
The next page only checks whether the current sort key is older than continue.

| Change while paging | Later page |
| --- | --- |
| A newer Run is created | It does not enter the current pagination. A new query shows it at the front. |
| `startTime` is unchanged | Return the current content when its turn arrives. |
| An unreturned object's `startTime` becomes newer than continue | This pagination does not return it. |
| A returned object's `startTime` becomes older than continue | A later page returns it again. |
| Live is deleted and a same-name archive remains | That archive joins later comparisons at its current sort key. |
| Process restart or another replica | The original continue continues the query. |

For example, page size 2 and order A, B, C. The first page returns A and B.
Meanwhile a newer E is created, and C's status changes while `startTime` stays
the same. The second page returns the updated C. E waits for a new query.
### 7. Get, Delete, Watch, and fidelity {#details-and-actions}

#### Get

1. Authorize by name and Get Kubernetes directly. A hit returns immediately
   and does not query Results.
2. Only a native 404 looks up the archive by namespace, kind, and name. A
   Kubernetes 403, timeout, or 5xx must not be turned into 404.
3. Read the current latest row from the name index, then read the complete
   Record.
4. Return 404 only when both sources confirm the object is absent. If live
   misses and Results is unavailable, return 503. If the archive is forbidden,
   return 403.

Get returns the current object. `resourceVersion=0` is a current read, the
same as omitting it. Only a non-empty value other than `0` is forwarded to
the live Get. If that pinned read fails, do not replace it with an archive.

#### Watch

Live synchronization reuses this Watch. An event does not trigger another
List. The upstream is a dynamic Watch continued from the live resourceVersion
in the List response. Downstream event types remain `ADDED`, `MODIFIED`,
`DELETED`, `BOOKMARK`, and `ERROR`. Rewrite a resource event against the
unified set before writing it. Do not forward it unchanged.

| Upstream event | Server handling | Downstream event |
| --- | --- | --- |
| `ADDED` | Remove the archive marker and forward the current live object. If the name lookup confirms a same-name archive with a different UID, forward that archive's `DELETED` first. | `ADDED`, with `DELETED` first when needed |
| `MODIFIED` | Remove the archive marker and forward the current live object. The object is still in etcd, so do not query Results. | `MODIFIED` |
| `DELETED` | Use the same name lookup as Get. If there is no Record, or the Record does not match this Watch's labelSelector or fieldSelector, forward the live object's `DELETED`. If a matching Record is found, forward `MODIFIED` with the archived copy and `resource.loaded.from.tektonResults=true`. | `DELETED` or `MODIFIED` |
| `BOOKMARK` | Advance the resourceVersion only. | Forward unchanged |
| `ERROR` | Keep the Kubernetes error. | Forward unchanged, including 410 from resourceVersion compaction |

The written object's `metadata.resourceVersion` is the live event
resourceVersion that triggered it, not the old resourceVersion stored in the
archive. If a delete lookup is confirmed after a later event was already
forwarded, the catch-up event uses the newest live resourceVersion already
forwarded, so the client cursor does not move backward. The generation check,
resourceVersion selection, and write happen in one send. After a newer event
for the same name has been sent, discard an older generation's rewrite. Later
live events do not wait for this lookup, but a catch-up event's
resourceVersion must not be older than the newest live resourceVersion already
written.

Before deleting live, unified Delete sets
`enhancement.tekton.dev/unified-run-delete=true` on the object. Any replica
that sees a `DELETED` with this annotation does not publish the Record just
written back by the finalizer as `MODIFIED`. The session keeps looking up the
name and sends `DELETED` only after it confirms there is no Record. Without
the annotation, a Record that is found and still matches the Watch conditions
is sent as `MODIFIED`. A non-matching Record is sent as the live object's
`DELETED`. The in-process registration only reduces waiting on this Pod. It
does not replace the annotation.

The name lookup does not use List merge and does not enter the List archive
queue. It uses an independent short timeout. An index that is not ready, a
timeout, a Results failure, or bad data does not mean there is no archive: do
not forward `DELETED`, do not close the stream, and do not turn it into 410.
The session keeps looking up and sends the catch-up event after confirmation.
Other live events do not wait for this lookup. If the caller has no records
read permission, or Results is explicitly not installed, forward live-only
`DELETED`.

An archive change with no live event does not enter this stream. The next
List reads the current result. Watch does not accept continue or limit.
`keyword` is not passed to Watch. `sendInitialEvents` does not send archived
objects and must be paired with `NotOlderThan`. When `timeoutSeconds` is
omitted, Watch stays at 30 seconds. It does not use the List five-minute
safety cap and does not give 300 seconds to the apiserver. Flush per event.
Ingress disables stream buffering. The read and write idle timeout is 360
seconds, greater than 59 seconds. Client disconnect cancels downstream
immediately.

A detail view first uses unified Get, then subscribes to the same Watch.
`MODIFIED` replaces the current object. Only `DELETED` means both sources are
gone. A Results failure must not stop Watch for a running resource.

#### Delete

Delete the same-name objects that exist when the request starts, by
namespace, kind, and name. A UID precondition in the caller body is ignored
and is not forwarded to Kubernetes.

After merging the query and body and dropping UID preconditions, validate the
remaining DeleteOptions before any probe, marker, archive read, or delete.
An invalid `dryRun` returns 422 and changes nothing. The admission probe sets
`DryRun=All` only after that validation.

1. Check permissions before side effects. Run delete is required. When Results
   is installed, also check records delete and logs delete. If an empty Result
   container may be deleted, also check results delete. Without that
   permission, keep the empty container.
2. When Results is explicitly not installed, use only this caller's identity
   for the native Delete.
3. When Results is installed, first query the same-name Run Records through
   the name index. If the name index is unavailable, the query times out,
   Results fails, or a Record cannot be decoded, return 503. Do not delete
   live and do not report completion. A difference between `records.name` and
   the object UID is not bad data. The List skip cannot be used here.
4. After the query succeeds, and before writing the annotation or changing the
   archive, run an impersonated dry-run against live with the same caller
   identity. Forward grace period and propagationPolicy, and set
   `DryRun=All`. A denial returns that error. Do not write
   `enhancement.tekton.dev/unified-run-delete` and do not delete logs or
   Records. A live object that is already absent is not a denial. SAR is not
   this check. The dry-run cannot predict a later webhook race.
5. Write the annotation only after the dry-run passes. If there is no Record,
   do not delete the archive. If there is a Record, read the related Log
   Record by Run UID. The existing `getLogRecord` uses
   `data.spec.resource.uid`. If there is no Log Record, skip storage deletion.
   If there is a Log Record, take the content required by `log.ToStream` and
   delete log storage. A Record that cannot be decoded is bad data: return
   503 and do not delete live. After storage deletion succeeds, delete this
   Run Record and Log Record in the same Results transaction. Delete each row
   by `(parent, result_id, id)`, not by the full row snapshot. A watcher
   update of the same row still deletes that row. Zero affected rows is not
   success. If storage deletion fails, do not delete those Records and clear
   the annotation already written. Do not call DeleteLog after the row is
   gone, because it would read the Record again.
6. Then delete live. Delete by name with this caller's identity, forwarding
   grace period and propagationPolicy. Delete only the current kind. A child
   resource has a different name and is not deleted because the parent name
   matches. If this delete fails, clear the annotation so the marker does not
   remain on a live object that still exists. If live is already absent, it
   does not need to be cleared again.

Any failed step returns the corresponding error. The caller retries by the
same name. An explicit caller dry-run uses the same identity, sends only a
native dry-run to live, does not read the Results configuration, does not
query the archive, and does not delete Records or logs. Create, cancel,
update, and rerun continue to call the native API.

#### Objects and related data

A complete Record uses the unstructured JSON decoder and validates nested
fields and integer ranges. Stored v1 and v1beta1 are returned as v1. v1beta1
reuses the locked Tekton `ConvertTo`. If conversion drops unknown fields, fix
that first. Do not only change apiVersion. Keep the existing entries for
topology, childReferences, logs, Pod and Elasticsearch, and Events. A related
Run calls unified Get by name.

### 8. Errors and recovery {#errors}

The new routes return `metav1.Status`.

| Case | HTTP / behavior |
| --- | --- |
| Invalid credentials / no permission | 401 / 403 |
| Parameter, signature, or query does not match continue | 400 |
| Both sources confirm absence / native precondition conflict | 404 / 409 |
| Method or representation is not supported | 405 / 406 or 415 |
| The live set or one object exceeds the hard limit | 413 |
| A new List without filters hits Results not ready, the order index not ready, timeout, downstream permission, or a page response that cannot be parsed | 200, return live, and mark the reason in the response header. One bad record does not use this degradation. |
| A new List with keyword, labelSelector, or fieldSelector hits one of those archive failures | Do not degrade. Explicit `timeoutSeconds` expiry returns 504. When the deadline is omitted, safety-cap expiry returns 503, not Gateway Timeout. Failure or an index that is not ready returns 503. No permission returns 403. Do not return 200 containing only live objects. |
| Delete hits an unavailable name index, query timeout, Results failure, or bad data | 503. Do not delete live and do not report completion. |
| An existing mixed continue hits an archive failure again | 503 or 502. Keep the original token. Do not switch that continue to live-only. |
| Explicit request deadline, server safety cap, or unexpected exception | 504 / 503 / 500. Only expiry of a caller-supplied `timeoutSeconds` is 504. |

The `X-Tekton-Archive-State` response header uses `included`, `live-only`,
`disabled`, `unavailable`, `forbidden`, and `invalid-data`. Degradation also
sends `Warning: 299`. An empty continue only means the current identified
range is finished. It does not mean history is empty. The Gateway must pass
and expose the header.

After an archive failure on a mixed continuation, the frontend discards that
continue and starts a new `source=live` query. It replaces the current display
only after that query succeeds. When Watch receives 410 from Kubernetes
compaction, the standard client lists and watches again.

### 9. Performance and capacity {#capacity}

Ordinary pagination does not count the archive. Each page's archive read is
bounded by the page size, rows hidden by live names, and the scan budget.
`limit=0` means the caller asked for every result and has no first-page
performance promise.

| Limit | Starting value |
| --- | --- |
| One live collection | 50,000 objects or 32 MiB. Above that, 413. |
| One Record / response | 4 MiB / 16 MiB |
| Archive query timeout | 2 seconds for an unfiltered first read, then degrade. User search and filters use the request deadline and do not degrade to an unavailable historical range. |
| Request deadline | List, Get, and Delete use a five-minute safety cap when `timeoutSeconds` is omitted. Expiry returns 503. An explicit value is at most 60 seconds and expiry returns 504. Watch stays at 30 seconds when omitted. |

Identical Lists from the same caller share one build. Cancel that build when
there is no waiter. Before joining, each request authorizes records on its
own. The shared key includes a credential fingerprint and does not store the
raw token. Different tokens, groups, or extra do not share a result. An
archive denial on an unfiltered list returns live-only for that request and
does not join another request's archive page. Different callers or different
queries build separately. Do not return 429 because of concurrency. One
request is still bounded by the live collection, response size, and request
deadline.

The suggested target is first-page P95 within 3 seconds and continuation P95
within 500 milliseconds. It has not been measured. Acceptance must cover an
index that is not yet valid, a small-table sequential scan, a large-table
timeout, a low-hit filter, and a deep page. The default path must not read
the whole archive and then sort it.

### 10. Frontend {#frontend}

The shared `K8sApiService` and `K8SResourceList` stay unchanged. Add a thin
`RunResourceService`. Reuse the existing `API_PATH`, `clusterRewrite`, and
`HttpClient`.

| Call | Behavior |
| --- | --- |
| List | Request the enhancement collection URL. Pass keyword, field, labelSelector, limit, and continue unchanged. |
| Get / Delete | Append the name to the collection URL. Delete forwards grace period and propagationPolicy and does not forward a UID precondition. |
| List synchronization | Subscribe to the same URL, using the live resourceVersion from the response. Insert `ADDED` by sort key, replace `MODIFIED` by UID, and remove `DELETED`. An event does not trigger List. |
| Detail | Unified Get, then subscribe to the same Watch. Only `DELETED` means absent. |

The shared list component updates loaded rows from those events. `insertFn`
uses the same sort key and does not insert by name. Watch errors still make
the standard client list and watch again. A failed List keeps the old rows. A
short page is filled only from the List continue.

Show "never run" only when the state is `included` or `disabled`, there is no
filter, and items are empty. `unavailable`, `invalid-data`, and `live-only`
show that the historical range is unavailable even on HTTP 200. They must not
enter the create guide. `forbidden` is not an archive failure: show no
permission, still render only live, and do not enter the create guide. A
detail view shows absent only when both sources return 404. Show delete
success only after delete succeeds.

### 11. Configuration and metrics {#configuration}

Put the Results address and CA in the existing `EnhancementConfig.API`. The
Operator configures them. Remove the draft `TEKTON_RESULTS_API_URL`. Results
readiness does not affect enhancement startup, the controller, or live Get
and Watch.

An empty `results.url` means it is not installed now. Do not cache an empty
address, or a resolved non-empty address, as a process-lifetime state. Every
List, Get, Delete, and new Watch reads the ConfigMap again. An established
Watch keeps the client from the start of that connection and reads the new
configuration after reconnect. Replace the client when the address or TLS
configuration changes. When the URL is cleared, return to not installed, and
delete can continue with live only. If a CA is configured but cannot be read
or parsed, this archive call fails and does not fall back to the system roots.
A cached bundle is dropped when a later read fails, and the old transport is
closed. Do not keep using the old trust chain. When no CA is configured, still
use the system roots. The CA read uses the request context and does not hold
the shared client lock during the Secret read. One caller's cancellation does
not become another caller's trust failure. An empty `audience` uses the
mounted token. When it is non-empty, that token's `aud` must contain it.
Otherwise this archive call fails and does not send a token with the wrong
audience. enhancement does not issue its own projected token.

| Environment | Behavior |
| --- | --- |
| Results is available and the index is valid | Return the mixed result with state `included`. |
| Explicitly not installed | Return live with state `disabled`. |
| Index not ready, timeout, network, or permission failure | Without filters, return live with `unavailable` or `forbidden`. User search or filters do not degrade: explicit deadline expiry returns 504, omitted-deadline safety cap or failure returns 503, and no permission returns 403. |
| One record cannot be shown or converted | Skip that record. Return the rest with state `included`. |
| Results returns an invalid run record for the whole page | Without filters, return live with state `invalid-data`. User search or filters return 503 and do not mark the whole history unavailable. |

Reuse the existing logs and metrics registry. Record stage latency, candidate
count, degradation reason, and capacity rejection. Metric labels must not be
username, namespace, UID, Record name, or token.

## Upgrade, indexes, and rollback {#backfill}

Reuse the Results AutoMigrate entry and the 0011 background index maintenance.

1. Install the immutable SQL functions.
2. Create the order and name expression indexes concurrently in the
   background. The old read API stays available.
3. The new ordered query returns archives only after the index is
   `indisvalid=true`. Until then, unified List returns live.

Release Results functions and indexes first, then enhancement, then the
frontend. The Operator pins the accepted combination and delivers it offline.
Rollback stops the new ordered query. Existing indexes may remain. There is
no new column or table to clean up. Do not remove 0011 with this change.

## Component changes and reuse {#component-changes}

These are the implementation notes. Paths are relative to each repository.
The enhancement baseline is the [MR !65 draft][implementation-draft].

```text
product page -> RunResourceService -> existing Gateway -> enhancement
            -> Kubernetes current live List/Get/Watch/Delete
            -> Results ListRecords / Get by name / Delete by name
enhancement comparator -> live order
Results SQL -> archive order
Operator -> install, configuration, permissions, and version combination
```

### 1. Ordering rules {#changes-shared}

**Location:** enhancement keeps the Go comparator in
`enhancement-api/pkg/capabilities/runorder`. The Results `0013` patch keeps
the SQL functions. The two sides do not share a module and do not import each
other.

Live objects are ordered in enhancement memory. Archives are ordered by
PostgreSQL. Both sides must produce the same order for the same object, or
merge and keyset will duplicate or skip items. The rule covers both Run kinds,
v1 and v1beta1, time zones, missing time, invalid time, and same-second UID.
Comparison truncates to UTC seconds. Fractional seconds are removed before
conversion to `timestamptz`, so PostgreSQL does not round them. Do not use
`btrim`. Whitespace on either side is not a valid time. A missing or invalid
time uses `has_sort_time=0` and seconds `0`. Do not keep nanoseconds and do
not return NULL. When the rule changes, create the new function and index
first. Do not mix them before the new index is ready.

### 2. Enhancement {#changes-enhancement}

**Location:** `enhancement-api/pkg/capabilities/{runs,webservice,types}.go`.
Complex logic may be split into `runs_query.go`, `runs_watch.go`, and
`runs_delete.go` in the same package.

| Existing code | Change |
| --- | --- |
| `RunResource` and the two definitions | Keep GVR, Kind, and version mapping. Share one handler flow. |
| `Handler.Register` | Collection GET dispatches List or Watch by `watch`. A single resource adds DELETE. Continue to reject unsupported methods and DeleteCollection. |
| `parseRunQuery` | Give native parameters to ParameterCodec. Add only keyword, field, and the internal source. |
| `RunArchiveSource.List` | Change from reading every complete object to asking Results for one ordered page from the public continue. Keep REST, URL encoding, and token rotation. |
| `loadAndMergeRuns`, `getRun` | Change to merging the current live set with an archive keyset. Get is an independent lookup. It must not obtain one resource by listing everything. |

One List request runs in this order:

1. After authorization, page the current namespace live set with a dedicated
   dynamic client. If the object count or bytes cross the limit, return 413
   immediately and do not request the next page. On success, keep this live
   resourceVersion, the complete objects, and the name set.
2. Filter and sort live with enhancement's own comparator. Keep only objects
   whose sort key is older than continue.
3. Ask Results for one page older than the sort key. SQL has already removed
   older same-name Records. enhancement then removes current live names.
   Hidden rows do not count as returned objects. When the read must continue,
   move only the archive position `a`.
4. Compare the heads of the two ordered streams and take the newer one until
   the page is full, both sources are exhausted, or the scan or byte budget
   is reached. If the budget is exhausted and the archive is not finished,
   stop the page. `a` stays at the last scanned key. Do not write an older
   live object that has not been compared into `k`. The public continue `k`
   stops at the last returned object. It must not stop on an object that was
   only prefetched and not decided.
5. Return 200 only after bounded serialization succeeds. An archive failure
   on a new query keeps live and the state header. An archive failure on an
   existing mixed continue returns 503 and does not rewrite the original
   token's source.

Get calls Kubernetes first. Only 404 asks Results for the latest Record by
name. `resourceVersion=0` falls back like an omitted value. A non-empty value
other than `0` does not. Delete does not reuse List degradation. When Results
is installed, query by name first. An unavailable name index, timeout,
failure, or bad data returns 503 and does not delete live. After the query
succeeds, run an impersonated live dry-run with the caller identity. A denial
returns immediately, does not write the annotation, and does not delete the
archive. Only after it passes, write
`enhancement.tekton.dev/unified-run-delete`. If there is no Record, do not
delete the archive. If there is a Record, read the Log Record by Run UID, call
Stream.Delete with the extracted content, then delete the Run Record and Log
Record by primary key in a transaction, and then delete live with the caller
identity. If the real live delete fails, clear the annotation. Return
immediately on any failed step. Do not forward a UID precondition from the
caller body. Validate the remaining DeleteOptions before any of those steps.
An explicit caller dry-run uses the same identity, sends only a native dry-run
to live, and does not read the Results configuration.

Get and Delete reuse `parseTimeout`. Omitted or `0` is the five-minute safety
cap and expiry returns 503. An explicit value from 1 to 60 seconds returns 504
on expiry. An invalid, negative, or above-60 value returns 400.

Configuration is in `EnhancementConfig.API` in
`pkg/config/{enhancement_config,loader}.go`: Results address, CA, continue
signing key, and budgets. The signing key only prevents a forged continue. If
a CA is configured and a later read fails, drop the cache and close the old
transport. Do not keep the old trust chain. The CA read uses the request
context. Replicas share the same key. During rotation, keep the old
verification key until issued tokens are no longer used.

Kubernetes and Results deadlines and bytes are limited separately. enhancement
does not apply an application-level concurrency rejection to List. Identical
Lists from the same caller share a build. Cancel that build after the last
caller disconnects. Authorize with that request's token before sharing, and
use a credential fingerprint as the shared key. An archive timeout or circuit
break on List affects only the List archive branch. A failed Delete query
returns 503 and does not delete live.

Watch is implemented in `runs_watch.go`. It reuses dynamic Watch and the Get
name lookup:

1. Start the upstream Watch from the live resourceVersion returned by List.
   Cancel upstream when the client disconnects.
2. Flush BOOKMARK and Kubernetes ERROR unchanged. Do not write a Results
   failure as 410.
3. `DELETED` calls the name lookup with the namespace, kind, and name from
   the event. If there is no Record, or it does not match this Watch's
   labelSelector or fieldSelector, write the live object's `DELETED`. A
   matching Record writes `MODIFIED` with the archive annotation. If the
   object has `enhancement.tekton.dev/unified-run-delete=true`, a Record that
   is still present is not confirmation. Keep looking up until the Record is
   gone, then write `DELETED`. The written resourceVersion is at least the
   newest forwarded live resourceVersion. The generation check,
   resourceVersion selection, and write happen in one send. If a newer event
   for the same name was already sent, discard the old rewrite. If the lookup
   is not confirmed, do not write `DELETED`. Keep the connection, retry in the
   session, and send the catch-up event after confirmation. The delete rewrite
   belongs to this request. When the request ends, cancel the lookup, stop
   writing, and wait for the rewrite to exit. Do not use this ResponseWriter
   after that.
4. `ADDED` and `MODIFIED` write the live copy with the archive marker removed.
   They do not wait for an unfinished delete lookup. If `ADDED` confirms a
   same-name archive with a different UID, write that archive's `DELETED`
   first. A failed lookup still writes the live `ADDED`.
5. Adding the archive annotation and cleaning the live copy reuse the same
   handling as the List response.

### 3. Results {#changes-results}

Put the change in `tektoncd-results/.tekton/patches/`. Reuse the 0011 index
catalog, advisory lock, `CREATE INDEX CONCURRENTLY`, failure retry, and
`ANALYZE`. Do not add a table.

| Location | Change |
| --- | --- |
| `pkg/api/server/v1alpha2/index_migrate.go` | Add two expression indexes and the immutable functions. Validity is the PostgreSQL index state. |
| `lister/{order,offset,page_token}.go` and the page token proto | Add sort-key comparison and a token for `run_start_time desc`. The old order branches do not change. |
| `v1alpha2/records.go` | The new branch returns one page of complete Records by parent, kind, filter, latest same name, and keyset. It does not accept caller CEL. |
| `v1alpha2/records.go` delete path | A failed name query does not return an empty collection. Take the Log Record content and call Stream.Delete. After that succeeds, delete the Run Record and Log Record in a transaction by `(parent, result_id, id)`. Zero affected rows is not success. |
| `pkg/retention/job.go`, watcher, converter | Keep the existing write and cleanup flow. Expression indexes are maintained as rows change. Do not change `ToStorage`. |

The name query uses `NOT EXISTS` to exclude a newer same-name Record. `!label`
treats a missing labels object as an empty set. After the search-index
migration disables `statement_timeout`, reuse the 0011 session restore before
returning the connection to the pool. If restore fails, or the `SET` response
was lost, discard the physical connection. Tests use real PostgreSQL to verify
the index definition, keyset, and same-name selection. The fixture installs
the sort functions before creating expression indexes. A small-table sequential
scan is not a failure.

Delete by name covers only the current kind. Before deletion, read the related
Log Record by Run UID and call the existing Stream.Delete with the extracted
content. Delete the rows only after storage deletion succeeds. Do not call
DeleteLog after the row is gone, because it would read the Record again.
After deletion, correct the Result summary. Keep the container when other
Records remain. Also keep an empty container when results delete is absent.

### 4. Operator {#changes-operator}

**Location:** `components.yaml`, `values.yaml`, Results and enhancement
manifests, and `config/operator/add-rbac-verb-for-enhancement.yaml`.

- Write the Results address, CA, and budgets into the existing enhancement
  configuration, and mount a stable continue signing key. If an existing
  Secret has an empty `key`, fill it. Do not treat an empty Secret as usable.
- Install Run get, list, watch, and delete, namespace identity reads, and the
  impersonate permission required by this Delete.
- Keep Results optional. A failed check must not be treated as not installed
  and must not block a live read.
- Write Results install, disable, or address changes to
  `operator.tekton.dev/results-archive-hash` and include it in the Pipeline
  InstallerSet spec hash. A failed lookup keeps the previous annotation and
  the existing manifests.
- Pin the accepted combination of the rule package, Results, enhancement, and
  frontend. During upgrade, confirm the new index eventually becomes valid.
  Do not treat API startup as proof that the index is usable.

### 5. Common {#changes-common}

Do not change `K8sApiService`, `K8SResourceList`, Watch error handling, or
keyword rewriting. Detail does not call the native Tekton `watchResource`.
`RunResourceService` connects to the unified Watch and keeps the existing
mapping: `DELETED` is empty, and other events are objects.

### 6. Product frontend {#changes-frontend}

**Location:** `pipeline-v2-frontend/apps/service/src/app`, in
`constants/api-path.constants.ts`, `shared/services/archived.service.ts`, and
the Run pages.

`RunResourceService` becomes the unified entry. Remove the two-source paging,
merge, and Record decoding from `ArchivedResourceService`. Check call sites
before moving logs, Events, childReferences, and other helpers that are still
used.

| Scenario | Integration |
| --- | --- |
| Main list | A custom fetcher reads unified List. Name and labels keep the original parameters. Status stays a frontend filter. Track by UID. |
| Recent runs | Collect candidates with unified List, then group with the existing taskRef and label logic. Do not query per row. |
| Task, Hub, and Repository | Keep the existing labelSelector and local refinement. Continue normally. |
| List synchronization | Subscribe to unified Watch. Insert `ADDED` by sort key, replace `MODIFIED` by UID, and remove `DELETED`. An event does not trigger List. |
| Archive failure | An empty list that is not included or disabled shows that the range is unavailable. After a mixed continuation fails, start a new live query and replace the display only on success. |
| Detail | Unified Get, then subscribe to unified Watch. Only `DELETED` shows absent. |
| Delete | Use the existing permission service to check Run delete and records, logs, and results delete. Call unified Delete by name. Do not send a UID precondition. |

Related resources keep the existing childReferences and mapping. The Run
itself changes to unified Get and List. Cancel, create, edit, and rerun still
use the native write API.

### 7. Gateway {#changes-gateway}

The released object is enhancement `config/default/api-ingress.yaml`,
`Ingress/tektoncd-enhancement-api`. Both
`nginx.ingress.kubernetes.io/proxy-read-timeout` and `proxy-send-timeout` are
`360`. The same object also sets `alb.ingress.cpaas.io/proxy-read-timeout` and
`proxy-send-timeout` to `360`.

360 seconds is 60 seconds longer than the five-minute safety cap used when
List omits a deadline. When a search expires, the server can still write JSON
503. The gateway does not cut it into 504 first. Watch is 30 seconds when the
deadline is omitted and at most 60 seconds when explicit. 360 seconds is
greater than the 59-second idle lower bound. These values are idle time
between two reads or writes, not the total response duration.

The business path class is `cpaas-system`. ingress-nginx reads the nginx
annotation in seconds. The global template only changes
`spec.ingressClassName` to `global-alb2`. The annotations remain on this
Ingress. The current ALB converts a bare number from seconds into the Rule
`proxy_read_timeout_ms` and `proxy_send_timeout_ms`, and prefers
`alb.ingress.cpaas.io`. The live ConfigMap was not read, so the controller
default is not written here as 60 seconds.

Reuse the existing global and business clusterRewrite. Verify every verb, the
DELETE body, Status, the archive response header, Watch flush, and cancel on
disconnect.

### 8. Delivery dependencies {#changes-delivery}

| Unit | Behavior to prove first |
| --- | --- |
| Ordering rule | The enhancement Go comparator and the Results SQL are maintained separately. Both truncate to UTC seconds. SQL removes fractional seconds before conversion and does not use btrim. |
| Results patch | On real PostgreSQL: expression index, keyset, latest same-name selection, and transactional delete by name. |
| enhancement | Merge of the current live set with one archive page, failure degradation, Watch rewrite, and delete within one request. |
| Frontend | No change to the shared client. Event application, short pages, and the archive empty state are handled by the dedicated service. |
| Operator and Gateway | Two replicas, identity chain, optional install, index not ready, and offline upgrade. |

## Test plan {#test-plan}

| Layer | Must prove |
| --- | --- |
| Order | Both Run kinds, time zones, missing and invalid time, and same-second UID. The functions do not raise and do not return NULL. Go and SQL both truncate to seconds. |
| Merge | A same-name live object wins and is not affected by the filter. Same-name archives show only the latest. Unchanged `startTime` does not repeat a returned item when pages of different sizes are concatenated. A row whose `records.name` differs from the object UID is returned, as are the other archives. One record that cannot be shown does not turn the page into invalid-data. |
| Data changes | A newer object does not enter the current pagination. Unchanged `startTime` returns the current content on a later page. An unreturned object whose `startTime` becomes newer is not returned by this pagination. A returned object whose `startTime` becomes older is returned again on a later page. The original continue still works after a replica change. A source that does not match continue returns 400. |
| Index | An invalid order index makes an unfiltered List return live and unavailable. In the same state, Delete returns 503 and both live and archive remain. A small-table sequential scan can still return the archive. A large query timeout does not fall back to an unbounded full-table sort. The PostgreSQL fixture installs the sort functions before creating expression indexes. |
| Search | A keyword or label filter that takes more than 2 seconds still returns archive hits. Explicit `timeoutSeconds` expiry returns 504. When omitted, it is not cut to 504 at 30 seconds, and safety-cap expiry returns 503. Neither response is a live-only 200. An unfiltered list still degrades after 2 seconds. Label `!=` keeps records that do not have that label. A keyword of three or more characters plus a pipeline equality, and a dense equality label, do not rescan every hit on the next page. If the pipeline plan is not an ordered Index Scan, that SQL is not executed. |
| Get and Watch | A Results failure does not close Watch and is not turned into 410. Archive lookup by name returns the latest. Watch continues from the live resourceVersion. `resourceVersion=0` falls back to the archive after a live 404. A non-empty value other than `0` does not. When etcd deletion finds a Record, downstream receives `MODIFIED` with that live event's resourceVersion. When no Record is confirmed, it receives `DELETED`. An unconfirmed lookup does not send `DELETED`. Kubernetes 410 is preserved. |
| Delete | A name-query timeout also does not delete live. After a successful query, run the caller-identity live dry-run first. A denial writes no annotation and deletes no archive. After it passes, delete only live when there is no Record. When there is a Record, take the log location, clean storage, and then delete the Record by primary key. A watcher update of that row is still deleted. Zero affected rows is not success. A failed real live delete clears the annotation. A UID precondition is not forwarded. Invalid DeleteOptions, including an invalid `dryRun`, return 422 before any archive or live change. An explicit caller dry-run does not read the Results configuration and does not delete the archive. |
| Identity | If admission denies the caller, this delete fails. The archive and annotation stay unchanged even if the service account is allowed. SAR is not this check. |
| Frontend | keyword and field are forwarded unchanged. An archive exception does not enter "never run". Watch events are applied by UID and do not trigger List. |
| Capacity | Repeated identical Lists from the same caller build once. After the last caller disconnects, the build is cancelled, and a later identical List can build again. Simultaneous Lists from different callers each return and do not return 429 because of concurrency. |

Fakes cannot replace real PostgreSQL, the identity chain, CRDs, TLS, or the
Gateway.

## References and baselines {#references}

The core source check used these fixed versions. Later edits to this document
do not change those evidence baselines.

| Source | Location / use |
| --- | --- |
| [enhancement `f1c0a5a6`][enhancement-tree] | `enhancement-api/pkg/capabilities/{runs,webservice,types}.go` and `pkg/config/*`: draft, routes, and configuration |
| [frontend `e1888f47`][frontend-tree] | `archived.service.ts`, `api-path.constants.ts`, and Run pages: existing call boundary |
| [frontend `e490d728`][frontend-filter-tree] | Existing keyword, labelSelector, TaskRef, version, and local status filtering |
| [Results upstream `ecca90d6`][results-tree] | `proto/v1alpha2/api.proto`, `lister/{order,offset}.go`, and `db/model.go`: existing protocol and pagination |
| [Results product `c8f90232`][results-product-tree] | [0011 patch][index-patch] and [patch registry][patch-registry]: background index maintenance |
| [Operator `142a99b3`][operator-tree] | Component list, optional install, and enhancement RBAC |
| [shared package `60ae583db29e`][auth-tree] | `requestauth` identity source and authorization chain |
| Locked Go dependencies | client-go and apimachinery `v0.35.3`; AlaudaDevops/pipeline `v1.0.3-alauda.1` |
| Locked frontend dependency | `@alauda-fe/common@1.4.11-prod-4.0.1-1`. This change does not modify those shared methods. |

Format reference: [TEP template](./catalog/template.md).
Database ordering reference: PostgreSQL [indexes and ORDER BY][pg-order].
Native parameters are compared with apimachinery v0.35.3
[ListOptions][k8s-list-options], [parameter validation][k8s-list-validation],
and [Kubernetes API concepts][k8s-api-concepts].

[issue]: https://jira.alauda.cn/browse/DEVOPS-44553
[related-issue]: https://jira.alauda.cn/browse/DEVOPS-44552
[implementation-draft]: https://code.alauda.io/alauda-pipelines/tektoncd-enhancement/-/merge_requests/65
[enhancement-tree]: https://code.alauda.io/alauda-pipelines/tektoncd-enhancement/-/tree/f1c0a5a63b8842345f349ea4514169b5f4e62b4a
[frontend-tree]: https://code.alauda.io/alauda-pipelines/pipeline-v2-frontend/-/tree/e1888f47aab2204cd7e2ae63cfca1b9ec5992d0c
[frontend-filter-tree]: https://code.alauda.io/alauda-pipelines/pipeline-v2-frontend/-/tree/e490d7286bc805d8a34d38502fa921345a6c4ac1
[results-product-tree]: https://code.alauda.io/alauda-pipelines/tektoncd-results/-/tree/c8f90232c874004fe781466b7c74e47e6cf8bfaa
[results-tree]: https://github.com/tektoncd/results/tree/ecca90d687d452096dfd48409f8d982e712a30b3
[index-patch]: https://code.alauda.io/alauda-pipelines/tektoncd-results/-/blob/c8f90232c874004fe781466b7c74e47e6cf8bfaa/.tekton/patches/0011-add-records-query-indexes.patch
[patch-registry]: https://code.alauda.io/alauda-pipelines/tektoncd-results/-/blob/c8f90232c874004fe781466b7c74e47e6cf8bfaa/.tekton/patches/README.md
[operator-tree]: https://code.alauda.io/alauda-pipelines/tektoncd-operator/-/tree/142a99b36b2adc17522207522cc60b673749c5e2
[auth-tree]: https://github.com/AlaudaDevops/pkg/tree/60ae583db29e
[pg-order]: https://www.postgresql.org/docs/14/indexes-ordering.html
[k8s-list-options]: https://github.com/kubernetes/apimachinery/blob/v0.35.3/pkg/apis/meta/v1/types.go
[k8s-list-validation]: https://github.com/kubernetes/apimachinery/blob/v0.35.3/pkg/apis/meta/internalversion/validation/validation.go
[k8s-api-concepts]: https://kubernetes.io/docs/reference/using-api/api-concepts/
