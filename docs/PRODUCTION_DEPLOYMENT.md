# Production Deployment Guide

Complete guide for deploying Churn MLOps platform to production using GitHub Actions and ArgoCD.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Repository Setup](#repository-setup)
3. [Kubernetes Cluster Setup](#kubernetes-cluster-setup)
4. [ArgoCD Installation](#argocd-installation)
5. [GitHub Actions Configuration](#github-actions-configuration)
6. [Deploy to Staging](#deploy-to-staging)
7. [Deploy to Production](#deploy-to-production)
8. [Monitoring & Observability](#monitoring--observability)
9. [Rollback Procedures](#rollback-procedures)
10. [Troubleshooting](#troubleshooting)

## Prerequisites

### Tools Required

- `kubectl` (v1.25+)
- `helm` (v3.10+)
- `argocd` CLI (v2.8+)
- `docker` (v20.10+)
- Git
- GitHub account with repository access

### Kubernetes Cluster

- Kubernetes 1.25+
- At least 3 worker nodes (production)
- Storage provisioner (for PVCs)
- Ingress controller (nginx recommended)
- cert-manager (for TLS certificates)

## Repository Setup

### 1. Fork/Clone Repository

```bash
git clone https://github.com/yourusername/churn-mlops-prod.git
cd churn-mlops-prod
```

### 2. Update Configuration

Update the following files with your values:

**GitHub Actions (`.github/workflows/cd-build-push.yml`)**:
```yaml
env:
  REGISTRY: ghcr.io
  IMAGE_NAME_ML: <your-org>/churn-mlops-prod-ml
  IMAGE_NAME_API: <your-org>/churn-mlops-prod-api
```

**ArgoCD Applications** (`argocd/*/application.yaml`):
```yaml
spec:
  source:
    repoURL: https://github.com/<your-org>/churn-mlops-prod.git
```

**Helm Values** (`k8s/helm/churn-mlops/values-*.yaml`):
```yaml
image:
  repository: <your-org>/churn-mlops-prod
```

### 3. Configure Secrets

#### GitHub Secrets

Go to `Settings > Secrets and variables > Actions` and add:

- `GITHUB_TOKEN` (automatically available)
- `SLACK_WEBHOOK_URL` (optional, for notifications)
- `KUBECONFIG` (optional, for direct kubectl access)

#### Kubernetes Secrets

```bash
# Create namespace
kubectl create namespace churn-mlops-staging
kubectl create namespace churn-mlops-production

# Create image pull secret (if using private registry)
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<your-username> \
  --docker-password=<your-token> \
  -n churn-mlops-staging

kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<your-username> \
  --docker-password=<your-token> \
  -n churn-mlops-production
```

## Kubernetes Cluster Setup

### 1. Install Ingress Controller

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update

helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace \
  --set controller.metrics.enabled=true \
  --set controller.podAnnotations."prometheus\.io/scrape"=true \
  --set controller.podAnnotations."prometheus\.io/port"=10254
```

### 2. Install cert-manager

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Create Let's Encrypt ClusterIssuer
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

### 3. Storage Class (Optional)

If your cluster doesn't have a default storage class:

```bash
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: kubernetes.io/aws-ebs
parameters:
  type: gp3
  fsType: ext4
allowVolumeExpansion: true
EOF
```

## ArgoCD Installation

### 1. Install ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for pods to be ready
kubectl wait --for=condition=Ready pods --all -n argocd --timeout=300s
```

### 2. Access ArgoCD UI

```bash
# Port forward
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Get initial password
ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
# Avoid printing passwords in shared terminals or CI logs.

# Login via CLI
argocd login localhost:8080 --username admin --password "$ARGOCD_PASSWORD" --insecure
```

### 3. Change Admin Password

```bash
argocd account update-password
```

### 4. Configure ArgoCD Repository

```bash
argocd repo add https://github.com/yourusername/churn-mlops-prod.git \
  --username <github-username> \
  --password <github-token>
```

### 5. Deploy ArgoCD Applications

```bash
# Create AppProject
kubectl apply -f argocd/appproject.yaml

# Deploy staging
kubectl apply -f argocd/staging/application.yaml

# Deploy production (after staging validation)
kubectl apply -f argocd/production/application.yaml
```

## GitHub Actions Configuration

### 1. Workflow Structure

The CI/CD pipeline consists of:

- **CI Workflow** (`.github/workflows/ci.yml`): Runs on PRs and develop branch
  - Linting & formatting
  - Unit tests
  - Security scanning
  - Docker build validation

- **CD Workflow** (`.github/workflows/cd-build-push.yml`): Runs on main branch
  - Build & push Docker images
  - Tag images appropriately
  - Update GitOps manifests

- **Release Workflow** (`.github/workflows/release.yml`): Runs on version tags
  - Create GitHub release
  - Generate changelog
  - Notify team

### 2. Triggering Builds

```bash
# Create a feature branch
git checkout -b feature/new-model

# Make changes and commit
git add .
git commit -m "feat: improve model accuracy"

# Push and create PR
git push origin feature/new-model
```

This triggers the CI workflow.

### 3. Merging to Main

When PR is merged to `main`:
1. CD workflow builds images
2. Images pushed to GitHub Container Registry
3. Helm values updated with new image tags
4. ArgoCD detects changes and syncs

### 4. Creating Releases

```bash
# Tag a release
git tag -a v1.2.3 -m "Release v1.2.3"
git push origin v1.2.3
```

This triggers:
- Release workflow
- Production deployment (if configured)

## Deploy to Staging

### 1. Verify ArgoCD Application

```bash
argocd app get churn-mlops-staging

# Check sync status
argocd app sync churn-mlops-staging --dry-run
```

### 2. Sync Application

```bash
argocd app sync churn-mlops-staging
```

### 3. Monitor Deployment

```bash
# Watch pods
kubectl get pods -n churn-mlops-staging -w

# Check API logs
kubectl logs -n churn-mlops-staging -l app.kubernetes.io/name=churn-mlops -f

# Check service
kubectl get svc -n churn-mlops-staging
```

### 4. Verify Deployment

```bash
# Port forward API service
kubectl port-forward -n churn-mlops-staging svc/churn-mlops-api 8000:8000

# Test health endpoint
curl http://localhost:8000/health

# Test prediction endpoint
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test123", "features": {...}}'
```

## Deploy to Production

### 1. Validate Staging

Before deploying to production, ensure staging is stable:

```bash
# Check staging health
argocd app get churn-mlops-staging

# Run smoke tests
kubectl run test-pod --rm -i --tty \
  --image=curlimages/curl \
  --restart=Never \
  -- curl http://churn-mlops-api.churn-mlops-staging:8000/health
```

### 2. Create Production Tag

```bash
git tag -a v1.0.0 -m "Production release v1.0.0"
git push origin v1.0.0
```

### 3. Update Production Values

Update `k8s/helm/churn-mlops/values-production.yaml`:
```yaml
image:
  tag: "v1.0.0"
```

Commit and push:
```bash
git add k8s/helm/churn-mlops/values-production.yaml
git commit -m "chore: update production to v1.0.0"
git push origin main
```

### 4. Sync Production

```bash
# Review changes
argocd app diff churn-mlops-production

# Sync
argocd app sync churn-mlops-production
```

### 5. Monitor Production

```bash
# Watch deployment
kubectl rollout status deployment/churn-mlops-api -n churn-mlops-production

# Check metrics
kubectl top pods -n churn-mlops-production

# View logs
kubectl logs -n churn-mlops-production -l app=churn-mlops-api --tail=100
```

## Monitoring & Observability

### 1. Prometheus & Grafana (Optional)

```bash
# Install kube-prometheus-stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace

# Access Grafana
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
```

### 2. Application Metrics

API exposes metrics at `/metrics` endpoint:

```bash
kubectl port-forward -n churn-mlops-production svc/churn-mlops-api 8000:8000
curl http://localhost:8000/metrics
```

### 3. ArgoCD Notifications

Configure notifications in `argocd-notifications-cm`:

```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-notifications-cm
  namespace: argocd
data:
  service.slack: |
    token: \$slack-token
  trigger.on-deployed: |
    - when: app.status.operationState.phase in ['Succeeded']
      send: [app-deployed]
  template.app-deployed: |
    message: Application {{.app.metadata.name}} deployed to {{.app.spec.destination.namespace}}
EOF
```

## Rollback Procedures

### Quick Rollback (ArgoCD)

```bash
# List history
argocd app history churn-mlops-production

# Rollback to previous version
argocd app rollback churn-mlops-production

# Rollback to specific revision
argocd app rollback churn-mlops-production 5
```

### Kubernetes Rollback

```bash
# Deployment rollback
kubectl rollout undo deployment/churn-mlops-api -n churn-mlops-production

# Check rollout status
kubectl rollout status deployment/churn-mlops-api -n churn-mlops-production
```

### Manual Rollback

```bash
# Revert image tag in values file
git revert <commit-hash>
git push origin main

# ArgoCD will auto-sync
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod status
kubectl describe pod <pod-name> -n churn-mlops-production

# Check events
kubectl get events -n churn-mlops-production --sort-by='.lastTimestamp'

# Check logs
kubectl logs <pod-name> -n churn-mlops-production
```

### ArgoCD Sync Issues

```bash
# Refresh application
argocd app get churn-mlops-production --refresh

# Hard refresh (clear cache)
argocd app get churn-mlops-production --hard-refresh

# Delete and recreate
argocd app delete churn-mlops-production
kubectl apply -f argocd/production/application.yaml
```

### Image Pull Errors

```bash
# Verify secret
kubectl get secret ghcr-secret -n churn-mlops-production -o yaml

# Recreate secret
kubectl delete secret ghcr-secret -n churn-mlops-production
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<username> \
  --docker-password=<token> \
  -n churn-mlops-production
```

### Network Issues

```bash
# Test pod-to-pod communication
kubectl run test-pod --rm -i --tty \
  --image=nicolaka/netshoot \
  -n churn-mlops-production \
  -- bash

# Inside pod, test DNS and connectivity
nslookup churn-mlops-api
curl http://churn-mlops-api:8000/health
```

## Best Practices

1. **Always test in staging** before production
2. **Use semantic versioning** for releases
3. **Enable monitoring and alerting**
4. **Regular backups** of persistent volumes
5. **Keep secrets out of Git** (use sealed-secrets or external secret management)
6. **Review ArgoCD diffs** before syncing
7. **Use resource limits and requests**
8. **Implement health checks** for all services
9. **Regular security scanning** of images
10. **Document all manual interventions**

## Support

For issues or questions:
- Check the [troubleshooting guide](#troubleshooting)
- Review ArgoCD logs: `kubectl logs -n argocd -l app.kubernetes.io/name=argocd-server`
- Check application logs in respective namespaces
- Consult the team documentation

## Additional Resources

- [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/configuration/overview/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Helm Documentation](https://helm.sh/docs/)
