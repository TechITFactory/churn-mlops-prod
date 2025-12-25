# 🧪 Testing Guide - Complete Walkthrough

This guide walks you through testing your production-grade MLOps platform at every stage.

## Table of Contents

1. [Local Testing](#1-local-testing)
2. [Docker Testing](#2-docker-testing)
3. [Kubernetes Local Testing (Minikube)](#3-kubernetes-local-testing)
4. [CI/CD Testing](#4-cicd-testing)
5. [ArgoCD Testing](#5-argocd-testing)
6. [Integration Testing](#6-integration-testing)
7. [Production Validation](#7-production-validation)

---

## 1. Local Testing

### Prerequisites Check

```bash
# Check Python version
python --version  # Should be 3.10+

# Check if all tools are installed
which kubectl helm docker argocd
```

### Test Python Code Locally

```bash
# Navigate to project directory
cd churn-mlops-prod

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements/base.txt
pip install -r requirements/dev.txt
pip install -r requirements/api.txt
pip install -e .

# Run linting
echo "✅ Testing Linting..."
ruff check .
black --check .

# Run unit tests
echo "✅ Testing Unit Tests..."
pytest tests/ -v

# Run security scanning
echo "✅ Testing Security..."
pip install bandit safety
bandit -r src/
safety check --json

# Test imports
echo "✅ Testing Imports..."
python -c "import churn_mlops; print('✅ Package imported successfully')"
```

**Expected Output**: All tests pass, no linting errors

---

## 2. Docker Testing

### Test Docker Builds

```bash
# Build ML image
echo "🐳 Building ML Docker image..."
docker build -f docker/Dockerfile.ml -t churn-mlops-ml:test .

# Verify ML image
docker images | grep churn-mlops-ml

# Test ML image
docker run --rm churn-mlops-ml:test python -c "import churn_mlops; print('✅ ML image works')"

# Build API image
echo "🐳 Building API Docker image..."
docker build -f docker/Dockerfile.api -t churn-mlops-api:test .

# Verify API image
docker images | grep churn-mlops-api

# Test API image (run in background)
docker run -d --name test-api -p 8000:8000 churn-mlops-api:test

# Wait for API to start
sleep 5

# Test health endpoint
echo "🧪 Testing API health endpoint..."
curl http://localhost:8000/health

# Check API logs
docker logs test-api

# Cleanup
docker stop test-api
docker rm test-api
```

**Expected Output**: 
- Images build successfully
- Health endpoint returns `{"status": "healthy"}` or similar

### Test with Docker Compose

```bash
# Start services
docker-compose up -d

# Check status
docker-compose ps

# Test API
curl http://localhost:8000/health

# View logs
docker-compose logs -f churn-api

# Cleanup
docker-compose down
```

---

## 3. Kubernetes Local Testing (Minikube)

### Setup Minikube

```bash
# Start Minikube
minikube start --cpus=4 --memory=8192 --driver=docker

# Verify cluster
kubectl cluster-info
kubectl get nodes

# Enable ingress
minikube addons enable ingress
```

### Test Helm Charts

```bash
# Validate Helm chart syntax
echo "📊 Validating Helm charts..."
helm lint k8s/helm/churn-mlops/

# Dry-run staging deployment
echo "🧪 Testing staging deployment (dry-run)..."
helm install churn-mlops-test ./k8s/helm/churn-mlops \
  --namespace churn-mlops-test \
  --create-namespace \
  --values k8s/helm/churn-mlops/values-staging.yaml \
  --dry-run --debug

# Check for template errors
helm template churn-mlops ./k8s/helm/churn-mlops \
  --values k8s/helm/churn-mlops/values-staging.yaml \
  > /tmp/rendered-manifests.yaml

# Validate rendered manifests
kubectl apply --dry-run=client -f /tmp/rendered-manifests.yaml
```

**Expected Output**: No errors, manifests valid

### Deploy to Minikube

```bash
# Create namespace
kubectl create namespace churn-mlops-local

# Install with Helm
helm install churn-mlops ./k8s/helm/churn-mlops \
  --namespace churn-mlops-local \
  --values k8s/helm/churn-mlops/values-staging.yaml \
  --set api.replicaCount=1 \
  --set api.resources.requests.cpu=100m \
  --set api.resources.requests.memory=128Mi

# Watch deployment
kubectl get pods -n churn-mlops-local -w

# Wait for ready
kubectl wait --for=condition=Ready pods --all -n churn-mlops-local --timeout=300s

# Check status
kubectl get all -n churn-mlops-local

# Describe pod if issues
kubectl describe pod -n churn-mlops-local <POD_NAME>

# Check logs
kubectl logs -n churn-mlops-local -l app.kubernetes.io/name=churn-mlops --tail=50
```

### Test the Deployed API

```bash
# Port forward to API
kubectl port-forward -n churn-mlops-local svc/churn-mlops-api 8000:8000 &

# Test health
curl http://localhost:8000/health

# Test metrics (if available)
curl http://localhost:8000/metrics

# Test prediction endpoint (example)
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test123",
    "features": {
      "total_sessions": 45,
      "total_minutes": 3200,
      "days_since_signup": 180
    }
  }'

# Stop port forward
pkill -f "port-forward.*8000"
```

### Cleanup Minikube

```bash
# Uninstall Helm release
helm uninstall churn-mlops -n churn-mlops-local

# Delete namespace
kubectl delete namespace churn-mlops-local

# Or stop Minikube completely
minikube stop
```

---

## 4. CI/CD Testing

### Test GitHub Actions Locally (using act)

```bash
# Install act (if not already)
# macOS: brew install act
# Linux: curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# List available workflows
act -l

# Test CI workflow
echo "🧪 Testing CI workflow..."
act pull_request -W .github/workflows/ci.yml

# Test specific job
act pull_request -j lint-and-format -W .github/workflows/ci.yml
```

### Trigger CI/CD on GitHub

```bash
# Create a test branch
git checkout -b test/ci-cd-validation

# Make a small change
echo "# Testing CI/CD" >> TEST.md
git add TEST.md
git commit -m "test: validate CI/CD pipeline"

# Push and watch GitHub Actions
git push origin test/ci-cd-validation

# Open browser to see workflow
# https://github.com/YOUR_ORG/churn-mlops-prod/actions
```

**Expected Behavior**:
- ✅ Lint and format checks pass
- ✅ Unit tests pass
- ✅ Security scans complete
- ✅ Docker builds succeed

### Test CD Pipeline (Dry-run)

```bash
# You can manually trigger CD workflow from GitHub UI
# Or merge a PR to main branch to trigger automatically

# Check the workflow file
cat .github/workflows/cd-build-push.yml

# Verify workflow syntax
# Go to: https://github.com/YOUR_ORG/churn-mlops-prod/actions
```

---

## 5. ArgoCD Testing

### Install ArgoCD on Minikube

```bash
# Create namespace
kubectl create namespace argocd

# Install ArgoCD
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ArgoCD to be ready
kubectl wait --for=condition=Ready pods --all -n argocd --timeout=600s

# Get ArgoCD password
ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d)
# Avoid printing passwords in shared terminals or CI logs.

# Port forward ArgoCD UI
kubectl port-forward svc/argocd-server -n argocd 8080:443 &

# Login with CLI
argocd login localhost:8080 \
  --username admin \
  --password "$ARGOCD_PASSWORD" \
  --insecure
```

### Test ArgoCD Application Deployment

```bash
# Update repository URL in manifests
export REPO_URL="https://github.com/YOUR_ORG/churn-mlops-prod.git"
sed -i "s|yourusername|YOUR_ORG|g" argocd/staging/application.yaml

# Apply AppProject
kubectl apply -f argocd/appproject.yaml

# Apply staging application
kubectl apply -f argocd/staging/application.yaml

# Check application status
argocd app get churn-mlops-staging

# Watch sync
argocd app sync churn-mlops-staging
argocd app wait churn-mlops-staging --timeout 600

# Check in UI
# Open: https://localhost:8080
# Login with admin / $ARGOCD_PASSWORD
```

### Test ArgoCD Sync and Self-Healing

```bash
# Make a manual change to test self-healing
kubectl scale deployment churn-mlops-api --replicas=5 -n churn-mlops-staging

# Watch ArgoCD detect and fix the drift
argocd app get churn-mlops-staging --refresh

# ArgoCD should automatically restore to desired state
kubectl get deployment churn-mlops-api -n churn-mlops-staging
```

### Test ArgoCD Rollback

```bash
# View history
argocd app history churn-mlops-staging

# Rollback to previous version
argocd app rollback churn-mlops-staging

# Verify rollback
argocd app get churn-mlops-staging
```

---

## 6. Integration Testing

### Create Integration Test Script

```bash
cat > tests/integration_test.sh << 'EOF'
#!/bin/bash
set -e

echo "🧪 Running Integration Tests..."

# Test 1: API Health
echo "Test 1: API Health Check"
HEALTH=$(curl -s http://localhost:8000/health)
if [[ $HEALTH == *"healthy"* ]] || [[ $HEALTH == *"ok"* ]]; then
    echo "✅ Health check passed"
else
    echo "❌ Health check failed"
    exit 1
fi

# Test 2: Metrics endpoint
echo "Test 2: Metrics Endpoint"
METRICS=$(curl -s http://localhost:8000/metrics)
if [[ ! -z "$METRICS" ]]; then
    echo "✅ Metrics endpoint working"
else
    echo "⚠️  Metrics endpoint not available"
fi

# Test 3: Prediction endpoint (if model exists)
echo "Test 3: Prediction Endpoint"
PREDICTION=$(curl -s -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "features": {}}' || echo "not ready")
echo "Prediction response: $PREDICTION"

echo "✅ All integration tests passed!"
EOF

chmod +x tests/integration_test.sh
```

### Run Integration Tests

```bash
# Port forward API
kubectl port-forward -n churn-mlops-staging svc/churn-mlops-api 8000:8000 &

# Run tests
./tests/integration_test.sh

# Stop port forward
pkill -f "port-forward.*8000"
```

---

## 7. Production Validation

### Pre-Production Checklist

```bash
# Create checklist script
cat > scripts/pre_production_check.sh << 'EOF'
#!/bin/bash

echo "🔍 Pre-Production Validation Checklist"
echo "========================================"

# Check 1: Secrets exist
echo "✓ Checking secrets..."
kubectl get secret ghcr-secret -n churn-mlops-production && echo "  ✅ Image pull secret exists" || echo "  ❌ Missing image pull secret"

# Check 2: Persistent volumes
echo "✓ Checking persistent volumes..."
kubectl get pvc -n churn-mlops-production && echo "  ✅ PVCs exist" || echo "  ⚠️  No PVCs found"

# Check 3: Ingress controller
echo "✓ Checking ingress controller..."
kubectl get pods -n ingress-nginx | grep Running && echo "  ✅ Ingress controller running" || echo "  ❌ Ingress controller not ready"

# Check 4: cert-manager
echo "✓ Checking cert-manager..."
kubectl get pods -n cert-manager | grep Running && echo "  ✅ cert-manager running" || echo "  ⚠️  cert-manager not found"

# Check 5: ArgoCD
echo "✓ Checking ArgoCD..."
kubectl get pods -n argocd | grep Running && echo "  ✅ ArgoCD running" || echo "  ❌ ArgoCD not ready"

# Check 6: Resource quotas
echo "✓ Checking resource quotas..."
kubectl describe namespace churn-mlops-production | grep -A 5 "Resource Quotas"

echo ""
echo "✅ Pre-production checks complete!"
EOF

chmod +x scripts/pre_production_check.sh
./scripts/pre_production_check.sh
```

### Smoke Tests in Production

```bash
# Test 1: Check pods are running
kubectl get pods -n churn-mlops-production
kubectl wait --for=condition=Ready pods --all -n churn-mlops-production --timeout=300s

# Test 2: Check API is accessible
kubectl port-forward -n churn-mlops-production svc/churn-mlops-api 8000:8000 &
sleep 3
curl http://localhost:8000/health
pkill -f "port-forward.*8000"

# Test 3: Check ingress
curl https://churn-api.YOUR_DOMAIN.com/health

# Test 4: Check metrics
curl https://churn-api.YOUR_DOMAIN.com/metrics

# Test 5: Load test (optional)
# Install hey: https://github.com/rakyll/hey
hey -n 100 -c 10 https://churn-api.YOUR_DOMAIN.com/health
```

---

## 🎯 Quick Test Commands

### Complete Local Test

```bash
# One-liner to test everything locally
make setup && make lint && make test && \
docker build -f docker/Dockerfile.api -t test:api . && \
docker build -f docker/Dockerfile.ml -t test:ml .
```

### Complete Kubernetes Test

```bash
# One-liner for Kubernetes testing
helm lint k8s/helm/churn-mlops/ && \
helm install test ./k8s/helm/churn-mlops/ \
  --dry-run --debug \
  --values k8s/helm/churn-mlops/values-staging.yaml
```

### ArgoCD Test

```bash
# Validate and sync
kubectl apply -f argocd/staging/application.yaml && \
argocd app sync churn-mlops-staging && \
argocd app wait churn-mlops-staging
```

---

## 📊 Testing Checklist

- [ ] ✅ Local Python tests pass
- [ ] ✅ Docker images build successfully
- [ ] ✅ Helm charts validate without errors
- [ ] ✅ Minikube deployment succeeds
- [ ] ✅ API responds to health checks
- [ ] ✅ GitHub Actions CI passes
- [ ] ✅ ArgoCD syncs successfully
- [ ] ✅ Staging environment works
- [ ] ✅ Integration tests pass
- [ ] ✅ Production deployment succeeds
- [ ] ✅ Monitoring dashboards show data
- [ ] ✅ Load tests complete successfully

---

## 🆘 Troubleshooting

### Common Issues

**Issue**: Docker build fails
```bash
# Solution: Check Dockerfile syntax and build context
docker build -f docker/Dockerfile.api --no-cache .
```

**Issue**: Helm chart validation errors
```bash
# Solution: Check YAML syntax
helm lint k8s/helm/churn-mlops/ --strict
```

**Issue**: Pods not starting
```bash
# Solution: Check events and logs
kubectl describe pod <POD_NAME> -n <NAMESPACE>
kubectl logs <POD_NAME> -n <NAMESPACE>
```

**Issue**: ArgoCD app out of sync
```bash
# Solution: Force refresh and sync
argocd app get <APP_NAME> --hard-refresh
argocd app sync <APP_NAME> --force
```

---

## 📚 Next Steps

After all tests pass:
1. ✅ Commit and push changes
2. ✅ Create PR to test CI/CD
3. ✅ Merge to main to deploy to staging
4. ✅ Tag release for production: `git tag -a v1.0.0 -m "First production release"`
5. ✅ Monitor deployment in ArgoCD
6. ✅ Run production smoke tests

**Happy Testing! 🎉**
