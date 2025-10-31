---
weight: 10
---

# Quick Start

## Verify Deployment and Functionality

Users can quickly deploy and verify the functionality of Tekton Hub using the integration testing feature.

## Environment Requirements

- Kubernetes Cluster (1.24+)
- kubectl CLI tool
- Access to a container image repository

## 1. Manual Execution Locally

Navigate to the test directory and execute the script:

```bash
cd test
bash test.sh
```

The script will perform the following steps:

1. Deploy the Tekton Pipeline Controller
2. Deploy the Tekton Hub API and database services
3. Wait for the services to be ready
4. Create a TaskRun for testing
5. Verify the successful execution of the TaskRun
6. Clean up test resources
