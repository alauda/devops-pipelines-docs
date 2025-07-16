# Component Update Guide

This document describes how to update components in the TektonCD Operator project using the automated update system. The project now uses an automated script to download and process component releases, eliminating the need for manual updates.

## Overview

The automated component update process includes the following steps:
1. Configure component information in `components.yaml`
2. Run the automated update script to download and process components
3. Review and commit changes

## Step 1: Configure Components in components.yaml

All component configurations are managed in the `components.yaml` file at the project root. This file defines:
- Component names and their revision/branch
- Remote paths for downloading release artifacts
- Local paths for organizing downloaded files
- Custom file names if needed

### 1.1 Current Component Configuration

```yaml
tektoncd-pipeline:
  revision: main
  releases: 
    - remote_path: pipeline
      local_path: tekton-pipeline

tektoncd-hub:
  revision: main
  releases: 
    - remote_path: api
      local_path: tekton-hub/api
    - remote_path: hub-info
      local_path: tekton-hub/hub-info

tektoncd-trigger:
  revision: main
  releases: 
    - remote_path: trigger
      local_path: tekton-triggers
    - remote_path: bindings
      local_path: tekton-triggers
      local_name: bindings.yaml
```

### 1.2 Configuration Fields Explained

- **`revision`**: The Git branch or commit hash to pull releases from
- **`releases`**: Array of release artifacts to download
  - **`remote_path`**: Path in the remote repository (e.g., `api`, `pipeline`)
  - **`local_path`**: Local directory structure for organizing files
  - **`local_sub_path`**: (Optional) Subdirectory within the local path, the final dir will be "${local_path}/${version}/${local_sub_path}"
  - **`local_name`**: (Optional) Custom filename (defaults to `release.yaml`)

## Step 2: Run Automated Update Process

### 2.1 Using make update-components

The project provides a `make` target to run the automated update process:

```bash
# Run the complete automated update process
make update-components
```

This command will:
1. Download all component values and release files
2. Extract version information from values files
3. Process files with kustomize
4. Merge component images into the project's `values.yaml`

### 2.2 Specifying Custom Branch/Revision

To use releases from your own branch or specific commit:

1. **Edit components.yaml**: Update the `revision` field for the component you want to update:

```yaml
tektoncd-hub:
  revision: your-feature-branch  # or specific commit hash
  releases: 
    - remote_path: api
      local_path: tekton-hub/api
    - remote_path: hub-info
      local_path: tekton-hub/hub-info
```

2. **Run the update process**:

```bash
make update-components
```

### 2.3 Update Process Details

The automated script performs the following operations:

1. **Download Phase**: Downloads all component files from the specified revision
2. **Image Replacement Phase**: Updates catalog image references
3. **Rendering Phase**: Processes files with kustomize and organizes them by version
4. **Image Merging Phase**: Extracts and merges component images into `values.yaml`

## Step 3: Adding New Components

### 3.1 Adding a Component Entry

To add a new component to the automated update process:

1. **Add component configuration** to `components.yaml`:

```yaml
your-new-component:
  revision: main  # or your target branch
  releases: 
    - remote_path: main
      local_path: your-component/main
    - remote_path: sidecar
      local_path: your-component/sidecar
      local_name: sidecar.yaml
```

2. **Run the update process**:

```bash
make update-components
```

### 3.2 Component Structure Requirements

For a component to work with the automated system, it must:

1. **Have a values/release.yaml file** containing:
   - `global.version` field with version information
   - `global.images` section with component images

2. **Provide release artifacts** at the specified remote paths

3. **Follow the expected URL structure**:
   ```
   https://build-nexus.alauda.cn/repository/alauda/devops/tektoncd-releases/{component}/{revision}/{remote_path}/release.yaml
   ```

### 3.3 Example: Adding a New Tekton Component

```yaml
tektoncd-new-component:
  revision: v0.1.0
  releases: 
    - remote_path: controller
      local_path: tekton-new-component/controller
    - remote_path: webhook
      local_path: tekton-new-component/webhook
    - remote_path: cli
      local_path: tekton-new-component/cli
      local_name: cli.yaml
```

## Step 4: Review and Commit Changes

### 4.1 Verify Generated Files

After running the update process, verify the generated files:

```bash
# Check updated values.yaml
grep -A 5 "your-component" values.yaml

# Verify generated manifest files
ls -la .ko/operator/kodata/your-component/

# Check component images were merged
yq '.global.images' values.yaml
```

### 4.2 Test the updates

Ensure the updated configuration works correctly:

```bash
# Run tests
make test

# Build the project
make build
```

### 4.3 Commit Changes

Commit the automated updates:

```bash
# Add all generated files
git add values.yaml .ko/operator/kodata/ config/

# Commit with descriptive message
git commit -m "feat: update components via automated update

- Update tektoncd-hub to v1.19.2
- Update tektoncd-pipeline to v0.65.5
- Merge component images into values.yaml
- Generated by automated build system"
```

## Update Output Structure

The automated update process generates the following structure:

```
.ko/operator/kodata/
├── tekton-hub/
│   └── 1.19.2/
│       ├── api/
│       │   └── release.yaml
│       └── hub-info/
│           └── release.yaml
├── tekton-pipeline/
│   └── 0.65.5/
│       └── pipeline/
│           └── release.yaml
└── ...

config/
├── values/
│   ├── tektoncd-hub-release.yaml
│   ├── tektoncd-pipeline-release.yaml
│   └── ...
└── tekton-hub/
    ├── api/
    │   └── release.yaml
    └── hub-info/
        └── release.yaml
```

## Troubleshooting

### Common Issues

1. **Download Failures**: Check if the component revision exists and has the expected release artifacts
2. **Version Extraction Issues**: Ensure the component's values file has a valid `global.version` field
3. **Kustomize Build Failures**: Verify the downloaded files contain valid kustomize configurations
4. **Image Merge Issues**: Check that component values files have a `global.images` section

### Debug Commands

```bash
# Check component configuration
yq 'keys' components.yaml

# Verify downloaded files
ls -la config/values/
ls -la config/tekton-*/

# Check version extraction
yq '.global.version' config/values/tektoncd-hub-release.yaml

# Verify image merging
yq '.global.images' values.yaml
```

## Migration from Manual Updates

If you were previously updating components manually:

1. **Remove manual configurations** from `values.yaml` that are now handled by the automated system
2. **Update components.yaml** to include all components you were manually managing
3. **Run the automated update** to generate the new structure
4. **Remove old manual files** that are no longer needed

## Important Notes

1. **Version Management**: The automated system extracts versions from component values files
2. **Image Deduplication**: Component images are automatically merged with prefixes to avoid conflicts
3. **Branch Flexibility**: You can easily switch between branches by updating the `revision` field
4. **Rollback**: Use Git to rollback to previous commits if needed

## Related Documentation

- [Component Configuration Reference](../configure/components.yaml.md)
- [Build System Architecture](../architecture/build-system.md)
- [Development Environment Setup](../component-quickstart/index.md)
