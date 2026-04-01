---
created: '2026-01-04'
updated: '2026-01-04'
weight: 16
---

# Component Upstream Upgrade Guide

## Background

Tekton components (such as `tektoncd-pipeline`, `tektoncd-chains`, `tektoncd-triggers`, etc.) periodically need to be upgraded to track upstream community releases. This ensures we can leverage new features, bug fixes, and security patches from the upstream Tekton project.

This document provides a comprehensive guide on how to upgrade a component's upstream dependency to a new version.

## Upgrade Overview

The component upgrade process involves the following key steps:

1. **Define Target Version**: Determine the target upstream version to upgrade to
2. **Update Submodule and Upstream**: Update the Git submodule to the target release branch
3. **Update Makefile and Download Release Files**: Update version references and fetch upstream release manifests
4. **Adapt Patches and Kustomize Configuration**: Ensure patches and kustomize configs work with the new version
5. **Validate CI and Integration Tests**: Ensure builds and community integration tests pass
6. **Integrate into TektonCD Operator**: Update operator integration and verify E2E tests

## Prerequisites

Before starting the upgrade process, ensure you have:

- **Write access** to the component repository
- **Familiarity** with the component's structure and customizations
- **Knowledge** of upstream changes between versions (review upstream release notes)
- **Local development environment** set up with required tools (git, make, kustomize, yq, etc.)

## Step-by-Step Upgrade Process

### Step 1: Define Target Version

Before starting the upgrade, clearly identify the target version you want to upgrade to.

**Example Scenario:**

Upgrading `tektoncd-chains` from `v0.25.x` to `v0.26.0`

**Key Actions:**

1. **Review Upstream Release Notes**: Visit the upstream repository's releases page
   - Example: [Tekton Chains Releases](https://github.com/tektoncd/chains/releases)
   - Review changes, new features, breaking changes, and deprecations

2. **Reference TektonCD Operator LTS Version**: Check the component versions in the operator's LTS release
   - Example: Check [components.yaml](https://github.com/tektoncd/operator/blob/release-v0.78.x/components.yaml) in the target operator release branch
   - This helps ensure version compatibility with the operator ecosystem
   - Aligns your upgrade with tested and validated component combinations

3. **Identify Target Release Branch**: Determine the corresponding release branch
   - Example: For version `v0.26.0`, the branch is typically `release-v0.26.x`

4. **Check Compatibility**: Verify compatibility with other Tekton components
   - Review upstream compatibility matrices
   - Check if Pipeline, Triggers, or other dependencies need updates

**Example Command to Check Current Version:**

```bash
# Check current submodule branch
cat .gitmodules

# Check current Makefile version
grep "^VERSION" Makefile
```

### Step 2: Update Submodule and Upstream Information

Update the Git submodule reference to point to the target upstream release branch.

#### 2.1 Standard Git Submodule Upgrade Process

Follow these steps to update the submodule:

```bash
# 1. Manually edit .gitmodules file to update the branch field
# Change: branch = release-v0.25.x
# To:     branch = release-v0.26.x
# You can edit manually or use sed:
sed -i '' 's/release-v0.25.x/release-v0.26.x/g' .gitmodules

# 2. Sync .gitmodules configuration to .git/config
git submodule sync --recursive

# 3. Initialize and update submodule to the latest commit on the specified branch
git submodule update --init --recursive --remote

# 4. Add changes to staging area
git add .gitmodules upstream

# 5. Check current submodule status
git submodule status

# 6. Commit the changes
git commit -m "chore: upgrade upstream submodule to release-v0.26.x"
```

#### 2.2 Explanation of Commands

- **`sed -i '' 's/...'`**: Updates the branch reference in `.gitmodules`
  - **macOS**: Use `sed -i '' 's/...'` (with empty string after `-i`)
  - **Linux**: Use `sed -i 's/...'` (without the empty string)
- **`git submodule sync`**: Synchronizes the `.gitmodules` configuration to `.git/config`
- **`git submodule update --remote`**: Updates the submodule to the latest commit on the configured branch
- **`git add .gitmodules upstream`**: Stages both the configuration file and the submodule pointer

#### 2.3 Verify the Update

```bash
# Check the submodule is on the correct branch
cd upstream
git branch -a
git log -1 --oneline

# Return to the main repository
cd ..
```

### Step 3: Update Makefile and Download Release Files

Update the component version in the `Makefile` and download the corresponding upstream release manifest.

#### 3.1 Update VERSION in Makefile

Edit the `Makefile` to update the version number:

```bash
# Example: Update VERSION from v0.25.0 to v0.26.0
# Edit Makefile manually or use sed:
sed -i '' 's/VERSION ?= v0.25.0/VERSION ?= v0.26.0/g' Makefile
```

**Example Makefile Configuration:**

```makefile
include base.mk

# VERSION is the version of Tekton Chains
VERSION ?= v0.26.0

# RELEASE_YAML is the URL to get the release.yaml
RELEASE_YAML ?= https://storage.googleapis.com/tekton-releases/chains/previous/${VERSION}/release.yaml

# RELEASE_YAML_PATH is the path to save the release.yaml
RELEASE_YAML_PATH ?= config/chain/release.yaml

# VERSION_CONFIGMAP_NAME is the name of the configmap that contains the component version
VERSION_CONFIGMAP_NAME ?= chains-info
```

#### 3.2 Download Upstream Release Manifest

Use the `make` target to download the upstream release manifest:

```bash
# Download the upstream release.yaml file
make download-release-yaml
```

This command will:
1. Download the `release.yaml` file from the upstream URL
2. Format it using `yq` for better git diff readability
3. Save it to the path specified in `RELEASE_YAML_PATH`

#### 3.3 Verify the Downloaded File

```bash
# Check the file was downloaded
ls -lh config/chain/release.yaml

# Verify version in the ConfigMap
yq '.metadata.name == "chains-info"' config/chain/release.yaml
yq 'select(.kind == "ConfigMap" and .metadata.name == "chains-info") | .data.version' config/chain/release.yaml
```

#### 3.4 Commit the Changes

```bash
# Add Makefile and the downloaded release.yaml
git add Makefile config/chain/release.yaml

# Commit the changes
git commit -m "chore: update version to v0.26.0 and download release manifest"
```

### Step 4: Adapt Patches and Kustomize Configuration

After updating to a new upstream version, patches and kustomize configurations may need to be adapted.

#### 4.1 Review Existing Patches

Check if existing patches apply cleanly to the new version:

##### 4.1.1 Prepare for Patch Conflict Detection

First, temporarily modify `base.mk` to add the `--reject` option to `git apply`. This will generate `.rej` files for patches that fail to apply, making it easier to manually resolve conflicts.

```makefile
apply-patches-default: ##@Patch Apply patches to upstream submodule, specify files via PATCHES
    @# Adding --reject option to git apply saves failed patches as .rej files
    @cd upstream && \
    set -e; \
    for patch in $(PATCHES); do \
        if [ -f "../$$patch" ]; then \
            echo "Applying $$patch ..."; \
            git apply --reject "../$$patch"; \
        else \
            echo "Warning: Patch file $$patch not found"; \
        fi \
    done
```

##### 4.1.2 Initial Conflict Detection

Run `make apply-patches-default` to check if all patches apply cleanly:

```bash
# Apply all patches to detect conflicts
make apply-patches-default
```

**If no conflicts occur:**
- All patches applied successfully
- You can skip to [Step 4.2](#42-update-kustomize-configuration)

**If conflicts occur:**
- You'll see error messages and `.rej` files in the `upstream` directory
- Proceed to the next section to resolve conflicts

##### 4.1.3 Resolve Patch Conflicts

When conflicts occur, you need to resolve them patch by patch:

**Step 1: Clean upstream changes**

```bash
# Clean all changes in upstream
make clean-patches-default
```

**Step 2: Apply patches one by one**

Apply each patch individually to identify which ones have conflicts:

```bash
# Apply the first patch
PATCHES=.tekton/patches/0001-set-insecure-skip-verify-based-on-configuration.patch make apply-patches-default
```

**Step 3: Resolve conflicts for the current patch**

If the patch has conflicts:

1. **Review `.rej` files**: Check the rejected hunks in `upstream/*.rej` files
   - `.rej` files contain the patch hunks that failed to apply
   - Each `.rej` file corresponds to a source file that had conflicts
   - The file format shows the original patch context and the failed hunk

   **Example .rej file structure:**
   ```diff
   ***************
   *** 10,15 ****  # Line numbers from the patch
     context line 1
     context line 2
   - old line to be removed
   + new line to be added
     context line 3
   ```

2. **Manually apply changes**: Edit the corresponding files in `upstream/` to apply the intended changes
   - Locate the file mentioned in the `.rej` filename (e.g., `controller.go.rej` → edit `controller.go`)
   - Find the relevant section in the source file using the context lines
   - Manually apply the changes (remove `-` lines, add `+` lines)
   - Adapt the changes if the surrounding code has changed in the new version

3. **Verify changes**: Ensure the modifications match the patch intent
   - Review what the original patch was trying to accomplish
   - Ensure your manual changes achieve the same goal
   - Delete the `.rej` files after resolving conflicts

**Step 4: Save the resolved patch**

After resolving conflicts, save the updated patch:

```bash
# Save changes in upstream as a new patch
make save-new-patch-default

# This creates .tekton/patches/new.patch
# Rename it to the original patch name
mv .tekton/patches/new.patch .tekton/patches/0001-set-insecure-skip-verify-based-on-configuration.patch
```

**Step 5: Commit changes in upstream (local only)**

**IMPORTANT**: After saving each patch, commit the changes in the `upstream` submodule (but don't push):

```bash
cd upstream
git add .
git commit -m "Apply patch: 0001-set-insecure-skip-verify-based-on-configuration"
cd ..
```

**Why commit in upstream?**
- Prevents multiple patches from being merged into a single patch file
- Maintains clear separation between different patches
- Makes it easier to track which changes belong to which patch

**Step 6: Continue with remaining patches**

After committing the first patch in upstream, proceed to the next patch:

```bash
# Apply the second patch
PATCHES=.tekton/patches/0002-another-patch.patch make apply-patches-default

# If conflicts occur, repeat steps 3-5:
# - Resolve conflicts manually
# - Save new patch: make save-new-patch-default
# - Rename: mv .tekton/patches/new.patch .tekton/patches/0002-another-patch.patch
# - Commit in upstream: cd upstream && git add . && git commit -m "..." && cd ..

# Continue with remaining patches...
```

**Note**: Since `make save-new-patch-default` resets all changes in the `upstream` directory, you must commit each resolved patch in `upstream` before moving to the next one. Otherwise, multiple patches may be combined into a single patch file.

##### 4.1.4 Final Verification

After resolving all patch conflicts, verify that all patches apply cleanly:

```bash
# Clean upstream and reapply all patches
make clean-patches-default apply-patches-default
```

If this command completes without errors, all patches have been successfully updated for the new version.

##### 4.1.5 Revert Temporary Changes

Don't forget to revert the temporary `--reject` modification in `base.mk` after resolving all conflicts:

```bash
# Revert base.mk to remove --reject option
git checkout origin/main base.mk
```

#### 4.2 Update Kustomize Configuration {#42-update-kustomize-configuration}

Review and update the `kustomization.yaml` files in the `config` directory:

```bash
# Example: config/chain/kustomization.yaml
# Ensure image replacements and patches are still valid
```

##### 4.2.1 Configure Container Resources

**IMPORTANT**: All containers must have resources (requests and limits) configured. This is required for proper resource management and scheduling in Kubernetes.

Create a `resources-patch.yaml` file to set resource limits and requests for all containers:

```yaml
# Example: config/chain/resources-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tekton-chains-controller
  namespace: tekton-chains
spec:
  template:
    spec:
      containers:
        - name: tekton-chains-controller
          resources:
            limits:
              cpu: 500m
              memory: 512Mi
            requests:
              cpu: 200m
              memory: 256Mi
```

**Guidelines for Resource Configuration:**

1. **Set appropriate resource requests and limits** based on:
   - Component's typical resource usage
   - Expected workload and scale
   - Available cluster resources

2. **Consider different resource profiles** for different components:
   - Controller components: typically need more resources
   - Webhook components: moderate resources
   - CLI/utility containers: minimal resources

3. **Test resource configurations** to ensure:
   - Containers don't get OOMKilled under normal load
   - Resource limits don't unnecessarily restrict performance
   - Requests are set appropriately for scheduling

4. **Update resources for all containers** in the deployment:
   - Main application containers
   - Init containers (if any)
   - Sidecar containers (if any)

#### 4.3 Test Kustomize Build

Verify the kustomize configuration builds successfully:

```bash
# Test kustomize build
kustomize build config/chain/
```

#### 4.4 Commit Configuration Changes

```bash
# Add updated patches and kustomize configs
git add patches/ config/

# Commit the changes
git commit -m "chore: adapt patches and kustomize config for v0.26.0"
```

### Step 5: Validate CI Pipeline and Integration Tests

Ensure the component builds successfully and passes all tests in the CI pipeline.

#### 5.1 Trigger CI Build

Push your changes to trigger the CI pipeline:

```bash
# Push changes to remote branch
git push origin your-upgrade-branch
```

#### 5.2 Monitor CI Pipeline

Monitor the pipeline execution to ensure:

1. **Image Build Phase**: All component images build successfully
   - Controller, webhook, and other component images
   - Patches apply correctly during the build

2. **Code Quality Checks**: Static analysis and linting pass
   - `golangci-lint` checks
   - Code coverage requirements met

3. **Unit Tests**: Component unit tests pass
   - `go test` execution
   - Upstream integration tests

4. **Security Scans**: Vulnerability checks pass
   - `govulncheck` for dependency vulnerabilities
   - Image security scans

#### 5.3 Run Tests Locally (Optional)

You can also run tests locally before pushing:

```bash
# Run upstream tests
cd upstream
go test -v ./...
cd ..
```

**Note**: This runs the upstream component's test suite. Make sure your patches don't break existing tests.

#### 5.4 Fix Issues

If the CI pipeline fails:

1. **Review Error Logs**: Identify the root cause
2. **Fix Issues**: Update code, patches, or configurations
3. **Commit Fixes**: Push updated changes
4. **Re-run Pipeline**: Verify fixes resolve the issues

   ```bash
   # Example: Fix and commit
   git add .
   git commit -m "fix: resolve build issues with v0.26.0 upgrade"
   git push origin your-upgrade-branch
   ```

### Step 6: Integrate into TektonCD Operator

After the component upgrade is validated, integrate the new version into the TektonCD Operator.

#### 6.1 Update components.yaml in TektonCD Operator

Update the `components.yaml` file in the `tektoncd-operator` repository to reference your upgraded component branch:

```yaml
# Example: Update tektoncd-chains revision
tektoncd-chain:
  revision: your-upgrade-branch  # or release branch after merging
  releases:
    - remote_path: chain
      local_path: tekton-chains
```

#### 6.2 Run Component Update in Operator

In the `tektoncd-operator` repository, run the automated component update:

```bash
# In tektoncd-operator repository
cd /path/to/tektoncd-operator

# Update components
make update-components
```

This will:
- Download the new component version
- Update `values.yaml` with new image references
- Generate release manifests in `.ko/operator/kodata/`

#### 6.3 Run E2E Tests

Execute the operator's E2E tests to ensure the upgraded component works correctly:

```bash
trigger E2E tests via CI pipeline
```

#### 6.4 Verify Component Installation

Check that the component installs and functions correctly:

1. **Deploy the Operator**: Install the operator with the new component version
2. **Verify Component Status**: Ensure the component pods are running
3. **Run Functional Tests**: Verify component functionality

   ```bash
   # Example: Check component pods
   kubectl get pods -A | grep tekton-chains

   # Example: Check component version
   kubectl get configmap chains-info -n <tekton-pipelines> -o yaml
   ```

#### 6.5 Create Pull Request in Operator

Once E2E tests pass:

1. **Create PR in Component Repository**: Merge your upgrade branch
2. **Create PR in Operator Repository**: Update `components.yaml` to use the merged branch
3. **Link PRs**: Reference the component PR in the operator PR description

## Post-Upgrade Tasks

### Update Documentation

Update relevant documentation to reflect the new version:

- **CHANGELOG.md**: Document the upgrade and any notable changes
- **Release Notes**: Prepare release notes for the upgraded version
- **Component Docs**: Update any component-specific documentation

### Monitor Production Rollout

After merging:

1. **Monitor Deployments**: Watch for issues in production environments
2. **Collect Feedback**: Gather feedback from users and operators
3. **Address Issues**: Quickly address any issues that arise

### Cleanup

Clean up temporary branches and artifacts:

```bash
# Delete local upgrade branch after merging
git branch -d your-upgrade-branch

# Delete remote upgrade branch
git push origin --delete your-upgrade-branch
```

## Common Issues and Troubleshooting

### Issue 1: Patches Fail to Apply

**Symptom:** Patches fail during image build or manual application

**Solution:**
1. Review upstream changes that affected the patched code
2. Update patches to match the new code structure
3. Test patches before committing

### Issue 2: Kustomize Build Fails

**Symptom:** `kustomize build` fails with validation errors

**Solution:**
1. Check for upstream changes in resource structure
2. Update `kustomization.yaml` to match new resource formats
3. Verify image references and patch targets

### Issue 3: Tests Fail After Upgrade

**Symptom:** Unit or integration tests fail with the new version

**Solution:**
1. Review upstream breaking changes
2. Update test expectations if behavior changed
3. Adapt custom code to new APIs or interfaces

### Issue 4: Version Mismatch in ConfigMap

**Symptom:** ConfigMap version doesn't match expected version

**Solution:**
1. Verify `VERSION` in Makefile is correct
2. Ensure `download-release-yaml` completed successfully
3. Check `VERSION_CONFIGMAP_NAME` matches the upstream ConfigMap

### Issue 5: E2E Tests Fail in Operator

**Symptom:** Operator E2E tests fail after component integration

**Solution:**
1. Check operator logs for component-related errors
2. Verify component manifest compatibility with operator
3. Review operator's component installation logic

## Best Practices

### Planning

1. **Review Release Notes**: Always review upstream release notes before upgrading
2. **Check Breaking Changes**: Identify and plan for breaking changes
3. **Test in Staging**: Validate upgrades in a staging environment first

### Execution

1. **Incremental Upgrades**: Prefer incremental version upgrades over large jumps
2. **Atomic Commits**: Keep commits focused on specific upgrade steps
3. **Descriptive Messages**: Use clear commit messages describing the changes

### Validation

1. **Comprehensive Testing**: Run all tests (unit, integration, E2E)
2. **Security Scanning**: Ensure no new vulnerabilities are introduced
3. **Performance Testing**: Verify performance hasn't regressed

### Documentation

1. **Document Changes**: Keep documentation up-to-date with version changes
2. **Update Examples**: Update example configurations if needed
3. **Share Knowledge**: Document lessons learned from complex upgrades

## Upgrade Checklist

Use this checklist to ensure all steps are completed:

- [ ] **Step 1: Define Target Version**
  - [ ] Review upstream release notes
  - [ ] Reference TektonCD Operator LTS components.yaml
  - [ ] Identify target release branch
  - [ ] Check compatibility with other components

- [ ] **Step 2: Update Submodule**
  - [ ] Update `.gitmodules` branch reference
  - [ ] Run `git submodule sync --recursive`
  - [ ] Run `git submodule update --init --recursive --remote`
  - [ ] Verify submodule is on correct branch
  - [ ] Commit submodule changes

- [ ] **Step 3: Update Makefile and Download Release Files**
  - [ ] Update `VERSION` in Makefile
  - [ ] Run `make download-release-yaml`
  - [ ] Verify release.yaml downloaded correctly
  - [ ] Verify version in ConfigMap
  - [ ] Commit Makefile and release.yaml

- [ ] **Step 4: Adapt Patches and Kustomize**
  - [ ] Check patches apply cleanly
  - [ ] Update patches if needed
  - [ ] Review kustomize configurations
  - [ ] Test `kustomize build`
  - [ ] Commit configuration changes

- [ ] **Step 5: Validate CI and Tests**
  - [ ] Push changes to trigger CI
  - [ ] Monitor CI pipeline execution
  - [ ] Ensure all builds pass
  - [ ] Ensure all tests pass
  - [ ] Fix any issues and re-run

- [ ] **Step 6: Integrate into Operator**
  - [ ] Update `components.yaml` in operator
  - [ ] Run `make update-components`
  - [ ] Run operator E2E tests
  - [ ] Verify component installation
  - [ ] Create PRs for both repositories

- [ ] **Post-Upgrade Tasks**
  - [ ] Update documentation
  - [ ] Prepare release notes
  - [ ] Monitor production rollout
  - [ ] Clean up temporary branches

## Related Documentation

- [Component Quick Start](../component-quickstart/index.md) - How to create a new component
- [Operator Integration Guide](./operator-integration.md) - How to integrate components into the operator
- [Branch Management Strategy](../component-quickstart/index.md#4-branch-management) - Understanding branch management
- [CI/CD Pipeline](../e2e/index.md) - Understanding the build pipeline

