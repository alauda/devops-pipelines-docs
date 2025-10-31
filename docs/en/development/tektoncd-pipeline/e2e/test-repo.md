# E2E Test Repository

## Overview

The e2e tests in this project depend on an internal public repository that mirrors the official Tekton Catalog. This repository is used for testing purposes and contains a subset of tasks and pipelines from the main catalog.

## Repository Information

- **Internal Repository**: `https://devops-gitlab.alaudatech.net/root/catalog-for-test`
- **Source Repository**: `https://github.com/tektoncd/catalog`
- **Synced Branch**: `main`

## Purpose

The internal catalog repository serves as a mirror of the official Tekton Catalog repository, providing:
- Faster access for internal development and testing
- Controlled environment for e2e tests
- Reduced dependency on external network connectivity

## Quick Sync Commands

### Initial Clone and Setup

```bash
# Clone the internal repository
git clone https://devops-gitlab.alaudatech.net/root/catalog-for-test.git
cd catalog-for-test

# Add the upstream remote
git remote add upstream https://github.com/tektoncd/catalog.git

# Fetch all branches from upstream
git fetch upstream
```

### Sync with Upstream

```bash
# Switch to main branch
git checkout main

# Pull latest changes from upstream main
git pull upstream main

# Push to internal repository
git push origin main
```

### One-liner Sync Command

```bash
# Quick sync command (run from catalog-for-test directory)
git checkout main && git pull upstream main && git push origin main
```