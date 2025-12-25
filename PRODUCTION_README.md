# 🚀 Churn MLOps - Production-Grade Deployment

[![CI](https://github.com/yourusername/churn-mlops-prod/actions/workflows/ci.yml/badge.svg)](https://github.com/yourusername/churn-mlops-prod/actions/workflows/ci.yml)
[![CD](https://github.com/yourusername/churn-mlops-prod/actions/workflows/cd-build-push.yml/badge.svg)](https://github.com/yourusername/churn-mlops-prod/actions/workflows/cd-build-push.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Production-grade MLOps platform for customer churn prediction with automated CI/CD, GitOps deployment, and comprehensive monitoring.

## 🌟 Features

- **🤖 Machine Learning Pipeline**: End-to-end ML pipeline from data ingestion to model serving
- **🔄 CI/CD Automation**: GitHub Actions for continuous integration and deployment
- **📦 GitOps Deployment**: ArgoCD for declarative, version-controlled infrastructure
- **🐳 Container-First**: Docker containers with multi-stage builds and security scanning
- **☸️ Kubernetes Native**: Helm charts for flexible, production-ready deployments
- **📊 Monitoring**: Prometheus metrics and Grafana dashboards
- **🔒 Security**: Automated vulnerability scanning, SBOM generation, and least-privilege access
- **🔄 Auto-Scaling**: Horizontal Pod Autoscaling based on CPU/memory metrics
- **📈 Model Registry**: Local model versioning with promotion workflow
- **⏰ Scheduled Jobs**: CronJobs for batch scoring, retraining, and drift monitoring

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Architecture](#-architecture)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Usage](#-usage)
- [CI/CD Pipeline](#-cicd-pipeline)
- [GitOps Workflow](#-gitops-workflow)
- [Deployment](#-deployment)
- [Monitoring](#-monitoring)
- [Contributing](#-contributing)
- [Documentation](#-documentation)

## 🚀 Quick Start

### Local Development

```bash
# Clone repository
git clone https://github.com/yourusername/churn-mlops-prod.git
cd churn-mlops-prod

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
make setup

# Run tests
make test

# Start API locally
make api
```

### Production Deployment

```bash
# Run automated setup script
chmod +x scripts/setup_production.sh
./scripts/setup_production.sh

# Or follow manual steps in docs/PRODUCTION_DEPLOYMENT.md
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         GitHub Repository                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Source     │  │    Docker    │  │     K8s      │          │
│  │    Code      │  │  Dockerfiles │  │    Helm      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└────────────┬────────────────────────────────────────────────────┘
             │
             ├─────────────┐
             │             │
             ▼             ▼
      ┌───────────┐  ┌───────────┐
      │  GitHub   │  │  GitHub   │
      │  Actions  │  │  Actions  │
      │   (CI)    │  │   (CD)    │
      └─────┬─────┘  └─────┬─────┘
            │              │
            │              ▼
            │        ┌───────────┐
            │        │Container  │
            │        │ Registry  │
            │        │(GHCR)     │
            │        └─────┬─────┘
            │              │
            ▼              ▼
      ┌───────────────────────────┐
      │        ArgoCD             │
      │   (GitOps Operator)       │
      └────────┬──────────────────┘
               │
               ▼
      ┌───────────────────────────┐
      │   Kubernetes Cluster      │
      │  ┌──────┐  ┌──────┐       │
      │  │ API  │  │  ML  │       │
      │  │ Pods │  │ Jobs │       │
      │  └──────┘  └──────┘       │
      └───────────────────────────┘
```

## 📦 Prerequisites

### Required Tools

- **Docker** (20.10+)
- **kubectl** (1.25+)
- **helm** (3.10+)
- **argocd** CLI (2.8+)
- **Python** (3.10+)
- **make**

### Cloud Infrastructure

- Kubernetes cluster (1.25+)
- 3+ worker nodes (production)
- Storage provisioner
- Load balancer support

### Accounts

- GitHub account with repository access
- Container registry (GitHub Container Registry recommended)

## 🔧 Installation

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/churn-mlops-prod.git
cd churn-mlops-prod
```

### 2. Configure Settings

Update configuration files with your values:

```bash
# Update GitHub org/username
find . -name "*.yaml" -exec sed -i 's/yourusername/YOUR_ORG/g' {} \;

# Update domain
export DOMAIN="your-domain.com"
sed -i "s/example.com/${DOMAIN}/g" k8s/helm/churn-mlops/values-*.yaml
```

### 3. Run Setup Script

```bash
chmod +x scripts/setup_production.sh
./scripts/setup_production.sh
```

Or follow the [detailed installation guide](docs/PRODUCTION_DEPLOYMENT.md).

## 🎯 Usage

### Local Development

```bash
# Install dependencies
make setup

# Run linting
make lint

# Run tests
make test

# Train model
make train

# Start API server
make api
```

### Kubernetes Deployment

```bash
# Deploy to staging
kubectl apply -f argocd/staging/application.yaml

# Check status
argocd app get churn-mlops-staging

# Deploy to production
kubectl apply -f argocd/production/application.yaml
```

### API Usage

```bash
# Health check
curl http://api.example.com/health

# Make prediction
curl -X POST http://api.example.com/predict \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "features": {
      "total_sessions": 45,
      "total_minutes": 3200,
      "days_since_signup": 180
    }
  }'
```

## 🔄 CI/CD Pipeline

### Continuous Integration

Triggered on pull requests and commits to `develop`:

1. **Linting & Formatting**: Ruff, Black, mypy
2. **Unit Tests**: pytest with coverage
3. **Security Scanning**: Bandit, Safety
4. **Docker Build**: Validation without push

**Workflow**: `.github/workflows/ci.yml`

### Continuous Deployment

Triggered on commits to `main`:

1. **Build Images**: Multi-stage Docker builds
2. **Security Scan**: Trivy vulnerability scanning
3. **Push to Registry**: GitHub Container Registry
4. **Update Manifests**: Helm values with new tags
5. **Trigger ArgoCD**: Automatic sync

**Workflow**: `.github/workflows/cd-build-push.yml`

### Release Process

Triggered on version tags (`v*.*.*`):

1. **Create Release**: GitHub release with changelog
2. **Tag Images**: Semantic versioning
3. **Update Production**: Production values file
4. **Notify Team**: Slack/email notifications

**Workflow**: `.github/workflows/release.yml`

## 🔄 GitOps Workflow

```bash
# 1. Create feature branch
git checkout -b feature/improve-model

# 2. Make changes and commit
git add .
git commit -m "feat: improve model accuracy"

# 3. Push and create PR
git push origin feature/improve-model

# 4. CI runs automatically

# 5. After approval, merge to main

# 6. CD builds and pushes images

# 7. ArgoCD syncs to staging

# 8. Validate in staging

# 9. Tag release for production
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0

# 10. ArgoCD syncs to production
```

See [GitOps Workflow](docs/GITOPS_WORKFLOW.md) for details.

## 🚢 Deployment

### Staging Environment

- **Namespace**: `churn-mlops-staging`
- **Replicas**: 1 API pod
- **Auto-sync**: Enabled
- **Domain**: `churn-api-staging.example.com`

### Production Environment

- **Namespace**: `churn-mlops-production`
- **Replicas**: 3+ API pods (auto-scaling)
- **Auto-sync**: Enabled with sync windows
- **Domain**: `churn-api.example.com`

### Deployment Commands

```bash
# Check ArgoCD apps
argocd app list

# Sync staging
argocd app sync churn-mlops-staging

# Sync production
argocd app sync churn-mlops-production

# Rollback
argocd app rollback churn-mlops-production
```

## 📊 Monitoring

### Prometheus Metrics

API exposes metrics at `/metrics`:

- Request count
- Request duration
- Error rates
- Model inference time
- Resource usage

### Grafana Dashboards

```bash
# Access Grafana
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80

# Credentials
Username: admin
Password: (retrieve from the Grafana secret)
kubectl get secret -n monitoring prometheus-grafana \
  -o jsonpath="{.data.admin-password}" | base64 -d
```

### ArgoCD UI

```bash
# Access ArgoCD
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Open browser
https://localhost:8080
```

### Logs

```bash
# API logs
kubectl logs -n churn-mlops-production -l app=churn-mlops-api -f

# Job logs
kubectl logs -n churn-mlops-production job/batch-score-xxx
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

See [Contributing Guidelines](CONTRIBUTING.md) for details.

## 📚 Documentation

- [Production Deployment Guide](docs/PRODUCTION_DEPLOYMENT.md)
- [GitOps Workflow](docs/GITOPS_WORKFLOW.md)
- [ArgoCD Setup](argocd/README.md)
- [API Documentation](docs/API.md)
- [Model Training Guide](docs/TRAINING.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## 🗂️ Project Structure

```
churn-mlops-prod/
├── .github/
│   └── workflows/          # GitHub Actions CI/CD
│       ├── ci.yml
│       ├── cd-build-push.yml
│       └── release.yml
├── argocd/                 # ArgoCD GitOps manifests
│   ├── staging/
│   ├── production/
│   └── appproject.yaml
├── docker/                 # Dockerfiles
│   ├── Dockerfile.api
│   └── Dockerfile.ml
├── k8s/
│   └── helm/
│       └── churn-mlops/   # Helm charts
│           ├── Chart.yaml
│           ├── values.yaml
│           ├── values-staging.yaml
│           └── values-production.yaml
├── src/
│   └── churn_mlops/       # Python package
│       ├── api/           # FastAPI application
│       ├── data/          # Data processing
│       ├── features/      # Feature engineering
│       ├── training/      # Model training
│       └── inference/     # Model serving
├── scripts/               # Automation scripts
├── tests/                 # Test suite
└── docs/                  # Documentation
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- ArgoCD team for GitOps excellence
- FastAPI for modern API framework
- Kubernetes community

## 📞 Support

- 📧 Email: support@techitfactory.com
- 💬 Slack: #churn-mlops-support
- 🐛 Issues: [GitHub Issues](https://github.com/yourusername/churn-mlops-prod/issues)

---

**Made with ❤️ by TechITFactory**
