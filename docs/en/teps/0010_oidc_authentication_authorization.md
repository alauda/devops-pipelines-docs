---
title: OIDC Authentication and Kubernetes RBAC Authorization
authors:
  - zcyu@alauda.io
creation-date: 2026-06-05T00:00:00.000Z
last-updated: 2026-06-05T00:00:00.000Z
status: proposed
---

# TEP-0010: OIDC Authentication and Kubernetes RBAC Authorization

## Summary

This proposal defines a reusable authentication and authorization mechanism for `tektoncd-enhancement` and other platform components. The mechanism uses an OIDC issuer for request authentication and Kubernetes `SubjectAccessReview` for authorization.

The recommended request flow is:

1. Extract the bearer token from the HTTP request.
2. Discover OIDC metadata from the configured issuer.
3. Fetch and cache the issuer JWKS.
4. Verify token signature, issuer, audience, and time claims.
5. Map trusted OIDC claims to Kubernetes `user` and `groups`.
6. Use the component ServiceAccount to create a Kubernetes `SubjectAccessReview`.
7. Let the current cluster's Kubernetes RBAC authorizer decide whether the mapped identity can access the requested resource.

This separates two responsibilities:

- Authentication: whether the token was issued by a trusted OIDC issuer, was issued for the expected audience, and is still valid.
- Authorization: whether the mapped Kubernetes identity has RBAC permission in the current cluster.

The design does not require the business cluster kube-apiserver to directly trust the OIDC issuer. This is important because validation showed that a business cluster may reject a platform OIDC token even when platform proxy APIs accept the same token.

## Motivation

`tektoncd-enhancement` exposes HTTP APIs that are consumed by platform UI and other components. These APIs need a reusable way to authenticate end users and authorize operations against Kubernetes resources without hard-coding platform-specific proxy behavior.

The mechanism must work in ACP environments while staying generic enough for other deployments:

- It should support OIDC issuers configured explicitly by the caller.
- It may use ACP `global-info` as a default configuration source.
- It must not hard-depend on `global-info`, a platform proxy API, a fixed ConfigMap field, or a fixed role claim.
- It should support air-gapped environments and private issuers.
- It should reuse Kubernetes RBAC as the final authorization decision point.

### Goals

- Verify OIDC bearer tokens using standard OIDC discovery and JWKS validation.
- Support flexible issuer, audience, CA, claim mapping, and clock-skew configuration.
- Map trusted OIDC claims to Kubernetes identities in a configurable way.
- Use Kubernetes `SubjectAccessReview` instead of `SelfSubjectAccessReview` when authorizing an end user represented by an OIDC token.
- Keep ACP compatibility by allowing default OIDC settings to be loaded from `global-info`.
- Keep platform-specific login and proxy behavior out of the reusable mechanism.
- Provide clear test coverage for token verification, claim mapping, and SAR authorization behavior.

### Non-goals

- Implement an OIDC login flow in `tektoncd-enhancement`.
- Require the business cluster kube-apiserver to accept platform OIDC tokens directly.
- Replace Kubernetes RBAC with OIDC roles.
- Treat platform-specific `roles` claims as Kubernetes groups unless explicitly configured.
- Make ACP `global-info` a required dependency.

## Validation Findings

Validation was performed in a test ACP environment on 2026-06-05. This section records only mechanism-level findings. It intentionally omits login URLs, user names, raw tokens, session data, and secret values.

### Global-info as a default configuration source

Both the global cluster and the business cluster exposed OIDC-related keys in `kube-public/global-info`:

- `oidcIssuer`
- `oidcClientID`
- `oidcClientSecretRef`
- `oidcResponseType`
- `oidcScopes`

The validation environment stored the issuer and client ID in `global-info`, while confidential client credentials were referenced from a Kubernetes Secret instead of being embedded directly in `global-info`.

Conclusion:

- `global-info` is useful as an ACP default discovery mechanism.
- A reusable library must still accept explicit configuration for issuer, audiences, CA data, and claim mapping.
- Missing platform proxy fields must not make the OIDC mechanism unusable when explicit OIDC configuration is available.

### OIDC discovery and JWKS

Discovery against `{issuer}/.well-known/openid-configuration` returned standard OIDC metadata, including:

- `issuer`
- `authorization_endpoint`
- `token_endpoint`
- `jwks_uri`
- supported signing algorithms
- supported PKCE challenge methods

JWKS exposed RSA signing keys. The `kid` in the token header matched a JWKS key and could be used for RS256 signature verification.

Conclusion:

- The reusable verifier should use OIDC discovery instead of requiring callers to hard-code JWKS URLs.
- JWKS should be cached and refreshed when key rotation causes a `kid` miss or a verification failure.

### Platform login details

The platform login flow used platform-specific wrapper endpoints around Dex and required PKCE for the tested client. Local credential login used a platform-specific encrypted form submission before exchanging the authorization code for tokens.

Conclusion:

- These login endpoints are platform implementation details.
- `tektoncd-enhancement` should behave as a resource server: it only needs to validate a bearer token that is already present on the incoming request.
- The reusable authentication path must not depend on platform login URLs, Dex UI endpoints, or console callback paths.

### Token claim shape

The tested administrator token contained identity claims similar to:

```json
{
  "iss": "https://issuer.example.com/dex",
  "aud": "platform-client",
  "email": "admin@example.com",
  "email_verified": true,
  "preferred_username": "admin@example.com",
  "name": "admin",
  "groups": null,
  "roles": [
    "platform-admin-system"
  ]
}
```

The tested namespace developer token contained identity claims similar to:

```json
{
  "iss": "https://issuer.example.com/dex",
  "aud": "platform-client",
  "email": "developer@example.com",
  "email_verified": true,
  "preferred_username": "developer@example.com",
  "name": "Developer",
  "groups": null,
  "roles": [
    "namespace-developer-system"
  ]
}
```

Conclusion:

- `preferred_username` and `email` were compatible with the existing ACP RBAC user bindings.
- The tested tokens did not contain a standard `groups` claim.
- The platform-specific `roles` claim is not the same concept as a Kubernetes `Role`.
- Using `sub` is a stronger generic identity strategy for new deployments, but existing ACP RBAC may not be bound to `sub`.
- ACP-compatible defaults may use `preferred_username` with fallback to `email`; generic deployments should explicitly choose `sub` when their RBAC bindings are created for `sub`.

### Direct Kubernetes API and platform proxy behavior

The same OIDC token produced different behavior depending on the endpoint:

- The business cluster direct API rejected the OIDC token.
- The platform proxy API accepted the OIDC token and mapped it to a Kubernetes user name.
- The returned Kubernetes groups contained only the standard authenticated group, not the platform-specific `roles` claim.

Conclusion:

- `SelfSubjectAccessReview` with the raw OIDC token is not a generic authorization path.
- Platform proxy authorization can work in ACP, but it is a platform-specific mechanism.
- The reusable mechanism should verify OIDC locally, map claims to Kubernetes user information, and authorize with `SubjectAccessReview` in the current cluster.

### RBAC behavior for mapped identities

Semantic SAR checks showed:

- Mapping the administrator token to the existing ACP user name matched current RBAC permissions.
- Mapping the same token to the token `sub` did not match the existing RBAC bindings.
- Adding the platform role claim as a Kubernetes group did not change the namespace developer result in the tested scenario.

The namespace developer account had `tasks.tekton.dev` permission only in its assigned project namespace:

| Namespace scope | Read verbs | Write verbs | Result |
| --- | --- | --- | --- |
| Assigned project namespace | yes | yes | The user can read and modify `tasks.tekton.dev` resources. |
| Other project namespaces | no | no | The user cannot access `tasks.tekton.dev` resources. |
| Platform system namespace | no | no | The user cannot access `tasks.tekton.dev` resources. |

The permission source was a namespace `RoleBinding` to the Kubernetes `User` subject. The referenced `ClusterRole` contained `tekton.dev` rules for `tasks`. Other project, system, or cluster-level bindings for the same user did not grant cross-namespace `tekton.dev/tasks` access.

Conclusion:

- Kubernetes RBAC decisions are driven by the `user` and `groups` strings passed to SAR.
- The tested platform's `roles` claim did not automatically become a Kubernetes RBAC group.
- For ACP compatibility, `preferred_username` is the practical default user mapping.
- `roles` or `groups` claims should be mapped to Kubernetes groups only when the caller explicitly configures that behavior and the cluster RBAC is bound to those group names.

## OIDC Concepts

### Issuer

The OIDC issuer is the unique identity provider that signs tokens. It is usually an HTTPS URL. A resource server must configure the expected issuer and reject tokens whose `iss` claim does not exactly match it.

Without issuer validation, a token signed by a different identity system could be accepted accidentally.

### Discovery

OIDC discovery is the standard metadata mechanism. A resource server normally fetches:

```text
{issuer}/.well-known/openid-configuration
```

The most important fields are:

- `issuer`: must match the configured issuer.
- `jwks_uri`: points to the signing keys used for token verification.
- `id_token_signing_alg_values_supported`: indicates supported token signing algorithms.
- `authorization_endpoint` and `token_endpoint`: useful for login clients, but not required by a resource server that only validates existing bearer tokens.

### JWKS and signature validation

JWKS means JSON Web Key Set. It is the public key set exposed by the issuer.

An OIDC token is usually a JWT:

```text
base64url(header).base64url(payload).base64url(signature)
```

The token header contains a `kid` that identifies the signing key. Verification should:

1. Read `kid` and `alg` from the token header.
2. Find the matching public key in JWKS.
3. Verify the signature with the configured algorithm.
4. Reject the request if verification fails.

The verifier should cache JWKS, but it must handle key rotation. When the `kid` cannot be found or verification fails because of stale keys, the verifier can refresh JWKS once and retry.

### Audience

The `aud` claim identifies the intended receiver of the token. A resource server must verify that `aud` contains one of the configured audiences, usually the OIDC client ID.

Without audience validation, a token issued for another service could be reused against `tektoncd-enhancement`.

### Time claims

The verifier should check:

- `exp`: expiration time. Expired tokens must be rejected.
- `nbf`: not before. Tokens used too early must be rejected when this claim exists.
- `iat`: issued at. Tokens with a clearly future issue time should be rejected.

A small clock skew, such as one or two minutes, is acceptable. The default must not be unlimited.

### ID tokens and access tokens

OIDC commonly uses two token types:

- ID token: proves the user's identity to the client and usually contains claims such as `sub`, `email`, and `preferred_username`.
- Access token: authorizes access to a resource server. Its format and claims are issuer-specific.

The tested environment used RS256 JWTs for both token types with similar claims. A generic implementation should not assume that every issuer's access token is a locally verifiable JWT. The initial reusable mechanism should clearly state whether it accepts ID tokens, access tokens, or both, and should only accept tokens that can be verified with the configured OIDC issuer and audience.

## Kubernetes Authorization Concepts

### User, group, role, and binding

Kubernetes authorization does not receive the OIDC token. It receives an already authenticated identity:

- `user`: a user name string.
- `groups`: group name strings.
- `extra`: optional structured identity data.

Kubernetes RBAC resources then apply:

- `Role` and `ClusterRole` describe allowed resources and verbs.
- `RoleBinding` and `ClusterRoleBinding` bind those permissions to `User`, `Group`, or `ServiceAccount` subjects.

OIDC `roles` and Kubernetes `Role` are different concepts. A `roles` claim is only a string from the identity provider. It affects Kubernetes RBAC only if the component maps it to a Kubernetes group and the cluster has RBAC bindings for that group.

### SelfSubjectAccessReview

`SelfSubjectAccessReview` checks whether the current Kubernetes request identity can perform an action.

If a component uses its own ServiceAccount client to create SSAR, the result is the component ServiceAccount's permission, not the end user's permission.

If a component uses the raw OIDC token to create a Kubernetes client and then creates SSAR, it works only when the kube-apiserver itself trusts the OIDC issuer. Validation showed this cannot be assumed.

### SubjectAccessReview

`SubjectAccessReview` allows the caller to explicitly specify the identity to check:

```yaml
apiVersion: authorization.k8s.io/v1
kind: SubjectAccessReview
spec:
  user: user@example.com
  groups:
    - team-a
  resourceAttributes:
    group: tekton.dev
    version: v1
    resource: tasks
    verb: get
    namespace: project-a
    name: example
```

Kubernetes does not require `spec.user` to be authenticated by the current kube-apiserver before SAR evaluation. If the component ServiceAccount is allowed to create `subjectaccessreviews`, Kubernetes authorizer matches the provided strings against current cluster RBAC.

This fits the proposed OIDC flow:

- The component verifies token authenticity.
- The component maps trusted claims to a Kubernetes subject.
- Kubernetes RBAC decides whether that subject can access the requested resource.

## Proposal

### Configuration model

The reusable mechanism should prefer explicit configuration and treat platform defaults as optional.

Suggested configuration shape:

```go
// OIDCAuthConfig describes how to verify OIDC tokens and map claims to Kubernetes identities.
type OIDCAuthConfig struct {
    IssuerURL        string
    Audiences        []string
    UsernameClaims   []string
    GroupsClaims     []string
    RolesClaims      []string
    UserPrefix       string
    GroupPrefix      string
    RequiredClaims   map[string]string
    CAFile           string
    CAData           []byte
    ClockSkewSeconds int
}
```

Recommended defaults:

- `IssuerURL`: may be loaded from `global-info.data.oidcIssuer` in ACP.
- `Audiences`: should be explicitly configured; ACP may default it from `global-info.data.oidcClientID`.
- `UsernameClaims`: ACP-compatible default is `preferred_username,email`; generic new deployments should prefer `sub`.
- `GroupsClaims`: disabled by default unless the issuer provides a standard group claim and RBAC is bound to it.
- `RolesClaims`: disabled by default; platform role claims may be enabled explicitly.
- `UserPrefix` and `GroupPrefix`: empty by default for ACP compatibility; new deployments may use prefixes such as `oidc:`.

The `global-info` integration should be an adapter, not a hard dependency:

```go
// GlobalInfoOIDCConfigLoader loads OIDC defaults from kube-public/global-info.
type GlobalInfoOIDCConfigLoader interface {
    LoadOIDCAuthConfig(ctx context.Context) (*OIDCAuthConfig, error)
}
```

### Bearer token extraction

The filter should:

- Read `Authorization: Bearer <token>`.
- Reject missing, malformed, or empty bearer tokens with 401.
- Avoid query token support by default because query tokens commonly leak into logs, browser history, and audit trails.
- Never log raw tokens.

Logs may record non-sensitive metadata such as whether a token was present, which issuer was configured, and which claim was selected as the user name.

### Token verifier

Verifier responsibilities:

1. Initialize OIDC provider metadata by discovery.
2. Fetch and cache JWKS.
3. Validate JWT signature and signing algorithm.
4. Validate `iss`.
5. Validate `aud`.
6. Validate `exp`, `nbf`, and `iat`.
7. Return trusted claims to the mapper.

Suggested interface:

```go
// TokenVerifier verifies a raw bearer token and returns trusted claims.
type TokenVerifier interface {
    Verify(ctx context.Context, rawToken string) (*VerifiedToken, error)
}

// VerifiedToken stores verified OIDC claims.
type VerifiedToken struct {
    Issuer   string
    Subject  string
    Audience []string
    Claims   map[string]any
}
```

Failure handling:

- Missing or malformed token: 401.
- Issuer, audience, signature, or time validation failure: 401.
- Discovery or JWKS temporary failure: 503 or a temporary error.
- Invalid server configuration: fail early at startup when possible; otherwise return 500 with clear logs.

### Claims mapper

The mapper converts trusted claims into a Kubernetes identity:

```go
// ClaimsMapper maps trusted OIDC claims to a Kubernetes authorization identity.
type ClaimsMapper interface {
    Map(ctx context.Context, token *VerifiedToken) (*KubernetesIdentity, error)
}

// KubernetesIdentity is the subject used in SubjectAccessReview.
type KubernetesIdentity struct {
    User   string
    Groups []string
    Extra  map[string]authv1.ExtraValue
}
```

Mapping rules:

- Evaluate `UsernameClaims` in order and use the first non-empty string claim.
- Return unauthorized when no configured username claim is present.
- If `email` is used as the user name, optionally require `email_verified=true`.
- Support group claims as string arrays.
- String group claims may support comma or whitespace splitting when explicitly enabled by the mapper.
- Map `roles` to groups only when `RolesClaims` is configured.
- Support optional group prefixes or filters so broad platform roles are not blindly used for component authorization.

ACP-compatible mapping:

```yaml
usernameClaims:
  - preferred_username
  - email
rolesClaims: []
userPrefix: ""
groupPrefix: ""
```

Generic new-deployment mapping:

```yaml
usernameClaims:
  - sub
userPrefix: "oidc:"
groupsClaims:
  - groups
groupPrefix: "oidc:"
```

When `sub` is used, RBAC bindings must also use the mapped `sub` value. Otherwise SAR will not match existing RBAC.

### SAR reviewer

The reviewer should use the component ServiceAccount client to create `authorization.k8s.io/v1.SubjectAccessReview`:

```go
// SubjectAccessReviewer checks whether an identity can access Kubernetes resources.
type SubjectAccessReviewer interface {
    Review(ctx context.Context, identity *KubernetesIdentity, attr authv1.ResourceAttributes) error
}
```

It must not use `SelfSubjectAccessReview` for end-user authorization.

Success requires:

- The SAR create request succeeds.
- `review.Status.Allowed == true`.

Failure behavior:

- `Allowed=false`: return forbidden with resource, subresource, verb, namespace, and name. Do not include token data.
- Non-empty `EvaluationError`: log it and deny access.
- SAR create failure: return a clear error, especially when the component ServiceAccount lacks `create subjectaccessreviews`.

The component ServiceAccount needs:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: oidc-subjectaccessreviewer
rules:
  - apiGroups:
      - authorization.k8s.io
    resources:
      - subjectaccessreviews
    verbs:
      - create
```

This permission only allows the component to ask whether an identity has a permission. It does not grant that identity access to business resources.

### REST filter adapter

A reusable REST filter should compose token extraction, OIDC verification, claim mapping, and SAR review:

```go
// OIDCSubjectReviewFilter validates an OIDC bearer token and authorizes the mapped identity by SAR.
func OIDCSubjectReviewFilter(
    ctx context.Context,
    verifier TokenVerifier,
    mapper ClaimsMapper,
    reviewer SubjectAccessReviewer,
    resourceAttGetter ResourceAttributeGetter,
) restful.FilterFunction
```

Existing authentication or self-review filters should keep their current behavior. Components should opt in to the OIDC SAR path explicitly.

For each request, the same mapped identity must be used for all required checks. A request must not perform one check with OIDC SAR and another check with a platform proxy or direct SSAR identity.

## Tektoncd-enhancement Integration Plan

The proposed mechanism should be integrated into `tektoncd-enhancement` as the authentication and authorization foundation for APIs that require end-user identity.

Recommended provider modes:

- `kubernetes-self`: keep current-cluster Kubernetes authentication and self-review behavior where that behavior is intentional.
- `platform-proxy`: keep platform proxy behavior for ACP-specific compatibility where required.
- `oidc-sar`: verify OIDC locally and authorize the mapped identity with current-cluster SAR.

The `oidc-sar` mode should:

- Accept explicit issuer, audience, CA, and claim mapping configuration.
- Optionally load issuer and audience defaults from ACP `global-info`.
- Avoid hard dependencies on platform proxy URL fields.
- Use the same mapped identity for every authorization check within one request.
- Build `ResourceAttributes` from the requested Tekton or enhancement resource.

For `tasks.tekton.dev` and other Tekton resources, authorization should use the exact Kubernetes API group, resource, namespace, name, and verb that represent the user's requested action. The validation results show why namespace must be included correctly: a namespace developer can have full Task permissions in one project namespace and no Task permissions elsewhere.

## Package Placement

The reusable code should live in a dedicated package instead of being hidden inside a generic Kubernetes client helper:

```text
oidcauth/
  config.go
  discovery.go
  verifier.go
  claims.go
  sar.go
  restful_filter.go
```

The package should represent OIDC authentication and Kubernetes authorization adaptation. It should not implement browser login.

### Dependency choice

The recommended implementation should use a mature OIDC verifier such as `github.com/coreos/go-oidc/v3/oidc`.

Rationale:

- OIDC discovery is security-sensitive.
- JWKS cache and key rotation behavior are easy to implement incorrectly.
- Issuer, signature, algorithm, audience, and time validation need consistent handling.

Using only a generic JWT library is possible, but it increases the amount of security logic that must be maintained locally.

## Security and Compatibility

### Required security checks

- Validate JWT signature.
- Validate `iss`.
- Validate `aud`.
- Validate `exp`.
- Validate `nbf` when present.
- Reject unsupported signing algorithms, including `none`.
- Never use unverified claims as Kubernetes RBAC identity.
- Never log bearer token values, session data, credential data, or encrypted login payloads.

### Recommended security configuration

- Custom CA bundle for private or air-gapped issuers.
- JWKS cache TTL and forced refresh on key mismatch.
- Clock skew.
- Required claims.
- Optional `email_verified` requirement.
- User and group prefixes.
- Group allowlist or denylist.
- Query-token support disabled by default.

### Compatibility strategy

- OIDC SAR should be explicitly enabled.
- Existing direct Kubernetes and ACP-specific proxy behavior should remain available where needed.
- `global-info` should be treated as a default loader, not a required runtime dependency.
- ACP proxy fields and OIDC fields should be validated separately so missing proxy configuration does not break explicit OIDC configuration.

## Test Plan

### Unit tests

Token verifier:

- Discovery succeeds and JWKS signature verification succeeds.
- Issuer mismatch returns 401.
- Audience mismatch returns 401.
- Expired token returns 401.
- Future `nbf` returns 401.
- Future `iat` returns 401.
- Missing `kid` refreshes JWKS once before failing.
- Unsupported algorithm is rejected.

Claims mapper:

- `preferred_username` falls back to `email`.
- `sub` mapping applies user prefix.
- `email_verified=false` is rejected when verification is required.
- `groups` array is mapped.
- `roles` is ignored by default.
- `roles` is mapped only when explicitly configured.
- Group filter is applied.
- Missing username claim returns an authentication error.

SAR reviewer:

- Creates `SubjectAccessReview`, not `SelfSubjectAccessReview`.
- `spec.user` and `spec.groups` come from mapped claims.
- `Allowed=true` allows the request.
- `Allowed=false` returns forbidden.
- SAR create permission errors are reported clearly.

REST filter:

- Missing bearer token returns 401.
- Token verification failure does not call SAR.
- Claim mapping failure does not call SAR.
- SAR forbidden does not call the downstream handler.
- Successful authentication and authorization call the downstream handler.

### Integration tests

Use a real cluster or envtest-style cluster to verify:

- OIDC SAR still works when the direct kube-apiserver does not accept the raw OIDC token.
- `preferred_username` or `email` mapping can match existing ACP RBAC.
- `sub` mapping fails until RBAC is bound to the mapped `sub`.
- Adding a RoleBinding for the mapped `sub` allows the request.
- A namespace developer can access `tasks.tekton.dev` only in the namespace where RBAC grants that permission.
- The component ServiceAccount receives a clear error when it cannot create `subjectaccessreviews`.

## Next Steps

1. Add the reusable OIDC verifier, claims mapper, SAR reviewer, and REST filter to the shared package.
2. Expose explicit configuration for issuer, audiences, claim mapping, CA data, clock skew, and required claims.
3. Add an optional `global-info` loader that fills only missing OIDC defaults.
4. Add an `oidc-sar` authentication and authorization mode for `tektoncd-enhancement`.
5. Use SAR authorization for `tektoncd-enhancement` endpoints that need end-user Kubernetes resource permissions.
6. Grant the `tektoncd-enhancement` ServiceAccount `create subjectaccessreviews` only when an endpoint uses SAR authorization.
7. Add focused unit tests and at least one real-environment validation path.

## Final Recommendation

`tektoncd-enhancement` should act as an OIDC-aware resource server instead of assuming the business cluster kube-apiserver accepts platform OIDC tokens directly.

The reusable model is:

- OIDC proves who the requester is.
- Claim mapping converts the OIDC identity into Kubernetes RBAC subject strings.
- Kubernetes SAR answers whether that subject can access the requested resource.

This design keeps the authentication boundary explicit, reuses current-cluster RBAC, works with ACP defaults, supports private air-gapped issuers, and avoids hard dependencies on platform-specific proxy behavior.
