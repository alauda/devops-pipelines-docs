---
created: '2026-09-20'
updated: '2026-09-20'
weight: 30
---

# Release Review and Closeout

The release process guide covers the engineering chain and the publication stages. This page
covers the gate between release testing and the final tag, and the work that closes a release
after the Cloud listing is live.

Do not treat a green pipeline, an uploaded package, or a generated draft as the end of a release.
The release is complete only when the evidence is reviewable and the externally visible records are
consistent with the artifact that was tested.

## 1. Non-functional gate

Non-functional testing is a release gate between Stage H and Stage I. It is not a replacement for
API/UI release testing or security scanning.

The three fixed areas are:

| Area | Evidence when newly run | Evidence when reused |
| :--- | :--- | :--- |
| High Availability | The current release line's report is archived and its merge request is merged | The owner approves a specified historical report and confirms that the component baseline, method and acceptance criteria are unchanged |
| Performance | The current release line's report is archived and its merge request is merged | The owner approves a specified historical report and confirms that the component baseline, method and acceptance criteria are unchanged |
| Stability | The current release line's report is archived and its merge request is merged | The owner approves a specified historical report and confirms that the component baseline, method and acceptance criteria are unchanged |

Reports belong under:

```text
plugins/tektoncd-operator/<vX.Y>/Test_Reports/Non_Functional/
  High_Availability/
  Performance/
  Stability/
```

Each area must have one of these explicit outcomes:

- **New run**: the report and archive merge request are complete.
- **Reuse**: the owner, historical report path, baseline, method and acceptance criteria are recorded.
- **Not applicable**: the owner explicitly confirms that this release does not require the area.

“Reference the previous release” is not an outcome. Do not start a HA, performance or stability
long run until the owner confirms that this release requires a new run.

The review page must copy the Stage N outcome. If the gate is unresolved, the review must remain
blocked or pending confirmation and Stage I must not start.

## 2. Entering the release review

Before scheduling the release review, collect evidence for the same final release identity:

| Area | Minimum evidence |
| :--- | :--- |
| Source and build | The final commit, tag, Bundle digest and final package names |
| Documentation | Release notes, lifecycle policy, upgrade path and feature maturity checks |
| Regression | API env1-env6 coverage, supported ACP minor coverage and merged report archives |
| Security | The static spreadsheet, dynamic runtime archive, scanner/database identity and disposition for every remaining finding |
| Non-functional | High Availability, Performance and Stability outcomes from Section 1 |
| Artifacts | Final ledger/channel commit, Bundle and image inventory, and amd64/arm64/ALL package checksums |
| Publication | J mirror evidence, K `devops-artifact` PR, L PipelineRun, and domestic/overseas listing confirmation |
| Compatibility | Release-notes support, actual regression coverage, Cloud product versions and Errata compatible versions |

The review checklist should keep these items as separate rows:

1. Automated testing
2. Upgrade matrix documentation
3. Product known issues
4. Product fixed issues
5. Product lifecycle
6. Release notes
7. Test cases
8. Manual regression record
9. Non-functional test report
10. Security test report
11. Plugin automated usage documentation
12. Bundle Channel configuration
13. Outstanding vulnerability registration
14. Release artifacts
15. Errata
16. ACP compatibility

Do not collapse documentation delivery, security, Errata or ACP compatibility into one generic
“release is ready” row. A missing evidence link or an unmerged report archive is a release review
blocker.

## 3. Closeout after the review

After the review is approved, execute and record the following actions in order:

1. **Release the Jira version**
   - Confirm the target release version and its issue set.
   - Change it to `Released` only after the review decision is recorded.

2. **Update the download template**
   - Update the approved template for the product version.
   - Verify that the template is published and can be read back.

3. **Complete Alauda Cloud configuration and approval**
   - Confirm that the Cloud metadata matches the final package and ACP compatibility decision.
   - For Stage L, record domestic and overseas review separately:

     | Environment | Review and publish | Final listing |
     | :--- | :--- | :--- |
     | Domestic | `https://cloudmanage.alauda.cn/appMarket/appReleaseManage` | `https://cloud.alauda.cn/app/385` |
     | Overseas | `https://cloudmanage.alauda.io/appMarket/appReleaseManage` | `https://cloud.alauda.io/app/126` |

   - A successful `upload-ac` PipelineRun is not sufficient. Both listings must be visible.

4. **Update the operator release record**
   - Add the product, version, supported ACP versions, release date, maintenance end date,
     release highlights and Errata references to the approved operator release record.

5. **Close Bugfix and Security Errata separately**
   - Bugfix Errata and Security Errata are different gates.
   - A published Bugfix Errata does not prove that Security Errata is unnecessary.
   - For each created Errata, record the code, type, compatible versions, status and the
     post-create details API read-back.
   - For remaining vulnerabilities, record fixed, false positive, known issue, not applicable,
     approved residual risk or release blocker. A registration file alone is not risk acceptance.

6. **Prepare and send the release email**
   - Generate the Outlook HTML draft only after the release date, package links, compatibility,
     Cloud listings and Errata references are verified.
   - Check the subject and To/Cc/Bcc before sending.
   - Sending is an irreversible external action and requires explicit confirmation.
   - After sending, record the time, recipients, subject and the mail record.

7. **Archive the release evidence**
   - Archive the review page, regression and security reports, non-functional evidence, final
     artifact commit, channel state, Errata read-backs, Cloud listing results and email record.
   - Do not use a temporary report URL as the only long-term evidence.

## 4. Required stage record

For every stage, retain the following fields in the release tracker:

| Field | Example content |
| :--- | :--- |
| Owner | The person responsible for executing or coordinating the stage |
| Input identity | Branch, commit, package version, ACP version or PR ref |
| Operation | Pipeline, comment command, MR/PR or manual console action |
| Output | Tag, digest, package, report, task ID, MR/PR or listing |
| Review state | Not started, in progress, passed, blocked, pending confirmation or merged |
| Evidence location | Durable repository path or read-back API |
| Notes | Known environment limitation, owner approval or unresolved discrepancy |

In particular:

- Stage J must record one task ID and final object verification per architecture.
- Stage K must record the GitHub PR number and whether it is merged.
- Stage L must record the PipelineRun, domestic review, overseas review, domestic listing and
  overseas listing independently.
- A downstream stage must not overwrite the real status of an upstream MR or PR.

## 5. Items that must remain explicitly unverified

The following items must not be filled with assumptions:

- The actual owner and invocation path for GA mirror synchronization in Stage J.
- The current CTYun dynamic security scan trigger and its authoritative procedure.
- The person or group that performs the domestic and overseas Cloud review.
- The final release date, channel set or ACP compatibility list when the source evidence disagrees.

When one of these is resolved, update this page and the main release guide in the same change that
changes the operational procedure.
