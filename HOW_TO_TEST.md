# 🚀 How to Test Your Setup - START HERE

This is your starting point for testing the production-ready MLOps platform.

## 🎯 Quick Start (5 Minutes)

### Option 1: Automated Testing (Recommended)

**For Linux/macOS:**
```bash
cd churn-mlops-prod
chmod +x scripts/quick_test.sh
./scripts/quick_test.sh
```

**For Windows PowerShell:**
```powershell
cd churn-mlops-prod
.\scripts\quick_test.ps1
```

This will test:
- ✅ Prerequisites (Python, Docker, kubectl, Helm)
- ✅ Python setup and dependencies
- ✅ Code quality (linting, formatting)
- ✅ Unit tests
- ✅ Docker builds
- ✅ API functionality
- ✅ Helm charts
- ✅ GitHub workflows
- ✅ ArgoCD manifests
- ✅ Documentation

### Option 2: Manual Step-by-Step

```bash
# 1. Test Python
python --version  # Should be 3.10+

# 2. Setup environment
python -m venv .venv
source .venv/bin/activate  OR source .venv/Scripts/activate # Windows: .venv\Scripts\activate
pip install -r requirements/dev.txt
pip install -e .

# 3. Run tests
make test

# 4. Build Docker images
docker build -f docker/Dockerfile.api -t test:api .
docker build -f docker/Dockerfile.ml -t test:ml .

# 5. Validate Helm
helm lint k8s/helm/churn-mlops/
```

## 📊 Testing Levels

### Level 1: Local Development (5 min)
```bash
# Test code locally
make setup
make lint
make test
```
**When**: Every code change
**Purpose**: Catch issues early

### Level 2: Docker Testing (10 min)
```bash
# Build and test containers
docker build -f docker/Dockerfile.api -t test:api .
docker run -d -p 8000:8000 --name test-api test:api
curl http://localhost:8000/health
docker stop test-api && docker rm test-api
```
**When**: Before committing
**Purpose**: Ensure containerization works

### Level 3: Kubernetes Testing (20 min)
```bash
# Test on Minikube
minikube start
helm install test ./k8s/helm/churn-mlops/ \
  --namespace test --create-namespace \
  --values k8s/helm/churn-mlops/values-staging.yaml
kubectl get pods -n test
```
**When**: Before deploying to staging
**Purpose**: Test K8s manifests

### Level 4: CI/CD Testing (Auto)
```bash
# Push to GitHub
git checkout -b test/my-feature
git add .
git commit -m "test: validate pipeline"
git push origin test/my-feature
# Create PR and watch GitHub Actions
```
**When**: For every PR
**Purpose**: Automated validation

### Level 5: Staging Deployment (30 min)
```bash
# Deploy with ArgoCD
kubectl apply -f argocd/staging/application.yaml
argocd app sync churn-mlops-staging
# Run integration tests
```
**When**: After PR merge
**Purpose**: Pre-production validation

### Level 6: Production Deployment (Manual)
```bash
# Tag release
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
# Deploy to production via ArgoCD
kubectl apply -f argocd/production/application.yaml
```
**When**: After staging validation
**Purpose**: Production release

## 🧪 Test Scenarios

### Scenario 1: First Time Setup
```bash
# 1. Clone repository
git clone https://github.com/yourorg/churn-mlops-prod.git
cd churn-mlops-prod

# 2. Run quick test
./scripts/quick_test.sh

# 3. Review results
# All tests should pass
```

### Scenario 2: Code Changes
```bash
# 1. Make changes
# ... edit files ...

# 2. Test locally
make lint
make test

# 3. Test Docker build
docker build -f docker/Dockerfile.api -t test:api .

# 4. Create PR
git checkout -b feature/my-change
git add .
git commit -m "feat: my change"
git push origin feature/my-change
# GitHub Actions will run automatically
```

### Scenario 3: Deploy to Staging
```bash
# 1. Merge PR to main
# GitHub Actions builds and pushes images

# 2. ArgoCD syncs automatically
argocd app get churn-mlops-staging

# 3. Verify deployment
kubectl get pods -n churn-mlops-staging
kubectl port-forward -n churn-mlops-staging svc/churn-mlops-api 8000:8000
curl http://localhost:8000/health
```

### Scenario 4: Production Release
```bash
# 1. Create release tag
git tag -a v1.0.0 -m "Production release"
git push origin v1.0.0

# 2. Release workflow runs
# Check: https://github.com/yourorg/churn-mlops-prod/releases

# 3. Deploy to production
kubectl apply -f argocd/production/application.yaml
argocd app sync churn-mlops-production

# 4. Verify
kubectl get pods -n churn-mlops-production
```

## 📋 Testing Checklist

Before deploying to production, verify:

### Code Quality
- [ ] All unit tests pass (`pytest`)
- [ ] Linting passes (`ruff check .`)
- [ ] Formatting correct (`black --check .`)
- [ ] No security issues (`bandit -r src/`)
- [ ] Dependencies updated (`pip list --outdated`)

### Docker
- [ ] API image builds successfully
- [ ] ML image builds successfully
- [ ] Images run without errors
- [ ] Health endpoints respond
- [ ] No critical vulnerabilities (Trivy scan)

### Kubernetes
- [ ] Helm charts validate (`helm lint`)
- [ ] Templates render correctly (`helm template`)
- [ ] Resources have limits set
- [ ] Security contexts configured
- [ ] Ingress configured properly

### CI/CD
- [ ] CI workflow runs on PRs
- [ ] CD workflow builds images
- [ ] Release workflow creates releases
- [ ] Image tags are correct
- [ ] GitHub secrets configured

### ArgoCD
- [ ] Applications sync successfully
- [ ] Health status is "Healthy"
- [ ] No sync errors
- [ ] Rollback works
- [ ] Self-healing enabled

### Staging
- [ ] Pods are running
- [ ] API responds to requests
- [ ] Metrics available
- [ ] Logs are clean
- [ ] No crashloops

### Production
- [ ] Multiple replicas running
- [ ] Auto-scaling works
- [ ] TLS certificates valid
- [ ] Monitoring active
- [ ] Backups configured

## 🆘 Common Issues

### Issue: Tests fail locally
```bash
# Solution: Check Python version and dependencies
python --version
pip install -r requirements/dev.txt
pytest tests/ -v
```

### Issue: Docker build fails
```bash
# Solution: Clear cache and rebuild
docker builder prune
docker build --no-cache -f docker/Dockerfile.api -t test:api .
```

### Issue: Helm validation errors
```bash
# Solution: Check YAML syntax
helm lint k8s/helm/churn-mlops/ --strict
helm template test ./k8s/helm/churn-mlops/ --debug
```

### Issue: ArgoCD app won't sync
```bash
# Solution: Force refresh and check status
argocd app get churn-mlops-staging --hard-refresh
argocd app diff churn-mlops-staging
argocd app sync churn-mlops-staging --force
```

### Issue: Pods not starting
```bash
# Solution: Check events and logs
kubectl describe pod <POD_NAME> -n <NAMESPACE>
kubectl logs <POD_NAME> -n <NAMESPACE>
kubectl get events -n <NAMESPACE> --sort-by='.lastTimestamp'
```

## 📚 Detailed Documentation

For more details, see:
- **TESTING_GUIDE.md** - Complete testing procedures
- **PRODUCTION_DEPLOYMENT.md** - Production deployment guide
- **GITOPS_WORKFLOW.md** - GitOps workflow details
- **QUICK_REFERENCE.md** - Command cheat sheet

## 🎓 Learning Path

### Day 1: Local Testing
1. Run `quick_test.sh`
2. Review test results
3. Fix any failures
4. Understand the codebase

### Day 2: Docker & Kubernetes
1. Build Docker images
2. Test locally with Docker
3. Setup Minikube
4. Deploy to Minikube

### Day 3: CI/CD
1. Review GitHub Actions workflows
2. Create test PR
3. Watch CI/CD run
4. Understand the pipeline

### Day 4: ArgoCD
1. Install ArgoCD
2. Deploy staging application
3. Test sync and rollback
4. Configure notifications

### Day 5: Production
1. Run pre-production checklist
2. Deploy to production
3. Monitor deployment
4. Document runbook

## 🎯 Success Criteria

You're ready for production when:
- ✅ All automated tests pass
- ✅ Docker images build and run
- ✅ Staging environment stable for 24h
- ✅ Load tests completed
- ✅ Security scans clear
- ✅ Monitoring dashboards show data
- ✅ Rollback procedure tested
- ✅ Documentation complete
- ✅ Team trained on workflow

## 🚀 Next Steps After Testing

1. **Configure Production Values**
   - Update domains
   - Set resource limits
   - Configure secrets

2. **Setup Monitoring**
   - Install Prometheus/Grafana
   - Configure alerts
   - Setup dashboards

3. **Deploy to Production**
   - Follow deployment guide
   - Monitor closely
   - Document any issues

4. **Continuous Improvement**
   - Review metrics
   - Optimize resources
   - Update documentation

---

**Ready to test? Start with: `./scripts/quick_test.sh`** 🚀
