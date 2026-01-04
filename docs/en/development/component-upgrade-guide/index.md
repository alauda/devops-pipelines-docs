---
created: '2026-01-04'
updated: '2026-01-04'
weight: 15
---

# Component Upgrade Guide

## Background

The TektonCD Operator manages multiple Tekton components (such as `tektoncd-pipeline`, `tektoncd-chains`, `tektoncd-triggers`, etc.). These components periodically need to be upgraded to track upstream community releases and integrate the latest versions into the operator.

This guide provides comprehensive documentation on the complete component upgrade workflow, covering both upstream version upgrades and operator integration.

## Overview

The component upgrade process consists of two main phases:

1. **Upstream Upgrade**: Upgrading a component's upstream dependency to a new version in the component repository
2. **Operator Integration**: Integrating the upgraded component into the TektonCD Operator

These two phases work together to ensure that components stay up-to-date with upstream releases while maintaining stability and compatibility within the operator ecosystem.

## Upgrade Workflow

### Phase 1: Upstream Upgrade

This phase involves upgrading a Tekton component to track a new upstream release version. The work is performed in the component's dedicated repository (e.g., `tektoncd-pipeline`, `tektoncd-chains`).

**Key Activities:**
- Update Git submodule to target release branch
- Update Makefile version and download release manifests
- Adapt patches and kustomize configurations
- Validate builds and tests in CI pipeline

**Target Audience:**
- Component maintainers
- Developers upgrading component upstream dependencies

**Detailed Guide:** See [Upstream Upgrade Guide](./upstream-upgrade.md)

### Phase 2: Operator Integration

After a component has been upgraded to a new upstream version, it needs to be integrated into the TektonCD Operator. This phase uses the automated component update system to fetch and integrate component releases.

**Key Activities:**
- Update `components.yaml` configuration
- Run automated update scripts to download component releases
- Merge component images into operator's `values.yaml`
- Run E2E tests to validate integration

**Target Audience:**
- Operator maintainers
- Developers integrating component updates

**Detailed Guide:** See [Operator Integration Guide](./operator-integration.md)

## When to Use This Guide

### Use Upstream Upgrade Guide When:
- You need to upgrade a component's upstream dependency to a new version
- You are maintaining a component repository (e.g., `tektoncd-pipeline`)
- You need to adapt patches for a new upstream release
- You are tracking upstream community releases

### Use Operator Integration Guide When:
- You need to update component versions in the TektonCD Operator
- You are configuring component update automation
- You need to merge component images into the operator
- You are integrating newly released components

## Typical Workflow Example

Here's a typical workflow for upgrading a component and integrating it into the operator:

1. **Upstream Upgrade** (in component repository):
   ```bash
   # Example: Upgrading tektoncd-chains from v0.25.x to v0.26.0
   cd tektoncd-chains
   # Follow upstream upgrade guide steps...
   ```

2. **Operator Integration** (in tektoncd-operator repository):
   ```bash
   # After component upgrade is complete
   cd tektoncd-operator
   # Update components.yaml to reference upgraded component
   # Follow operator integration guide steps...
   ```

## Related Documentation

- [Component Quick Start](../component-quickstart/index.md) - How to create a new component from scratch
- [Component Strategy](../component-strategy/index.md) - Understanding component management strategy
- [E2E Testing Guide](../e2e/index.md) - Running end-to-end tests

## Support and Contributions

If you encounter issues during the upgrade process:
- Check the troubleshooting sections in each guide
- Review recent upstream release notes for breaking changes
- Consult the team for component-specific considerations
