# V1 Command Reference (What We Did)

This document contains every command run in V1 (`churn-mlops-prod`), extracted from the course notes.

---

## Path 1: Local Development

### Setup
```bash
# Clone repository
git clone https://github.com/TechITFactory/churn-mlops-prod.git
cd churn-mlops-prod

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements/base.txt
pip install -r requirements/dev.txt
pip install -r requirements/api.txt

# Install package
pip install -e .

# Verify
python -c "from churn_mlops.common.config import load_config; print('OK')"
```

### Run Pipeline
```bash
# Full pipeline with Makefile
make all

# Or step by step:
make data       # Generate + validate + prepare
make features   # Build features
make labels     # Build labels + training set
make train      # Train baseline + candidate
make promote    # Promote best model
make batch      # Batch score

# Quality checks
make lint
make test
```

### Run API
```bash
./scripts/run_api.sh
# Or directly:
uvicorn churn_mlops.api.app:app --host 0.0.0.0 --port 8000

# Test
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

---

## Path 2: Docker Local

### Build Images
```bash
export VER=0.1.4

# Build ML image
docker build -t techitfactory/churn-ml:$VER -f docker/Dockerfile.ml .

# Build API image
docker build -t techitfactory/churn-api:$VER -f docker/Dockerfile.api .
```

### Run Seed (Bind Mount)
```bash
docker run --rm \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/artifacts:/app/artifacts \
  techitfactory/churn-ml:$VER \
  bash -c "
    python -m churn_mlops.data.generate_synthetic &&
    python -m churn_mlops.training.train_baseline &&
    python -m churn_mlops.training.promote_model
  "
```

### Run API
```bash
docker run --rm -p 8000:8000 \
  -v $(pwd)/artifacts:/app/artifacts \
  techitfactory/churn-api:$VER

# Test
curl http://localhost:8000/ready
```

---

## Path 3: Kubernetes (Minikube)

### Start Cluster
```bash
minikube start --cpus 4 --memory 8192
```

### Deploy Core
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/configmap.yaml
```

### Run Seed Job
```bash
kubectl apply -f k8s/seed-model-job.yaml
kubectl -n churn-mlops wait --for=condition=complete job/churn-seed-model --timeout=600s
kubectl -n churn-mlops logs -f job/churn-seed-model
```

### Deploy API
```bash
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl -n churn-mlops wait --for=condition=ready pod -l app=churn-api --timeout=120s
```

### Test
```bash
kubectl -n churn-mlops port-forward svc/churn-api 8000:8000 &
curl http://localhost:8000/ready
```

### Deploy Automation
```bash
kubectl apply -f k8s/drift-cronjob.yaml
kubectl apply -f k8s/retrain-cronjob.yaml
kubectl -n churn-mlops get cronjobs
```

---

## Path 4: EKS (Terraform)

### Provision Cluster
```bash
cd terraform
terraform init
terraform apply -auto-approve
```

### Configure kubectl
```bash
aws eks --region us-east-1 update-kubeconfig --name churn-mlops
kubectl config set-context --current --namespace=churn-mlops
```

### Deploy (Plain Manifests)
```bash
kubectl apply -f k8s/plain/namespace.yaml
kubectl apply -f k8s/plain/pvc.yaml
kubectl apply -f k8s/plain/configmap.yaml
kubectl apply -f k8s/plain/seed-model-job.yaml
kubectl -n churn-mlops wait --for=condition=complete job/churn-seed-model --timeout=900s
```

### Deploy API + CronJobs
```bash
kubectl apply -f k8s/plain/api-deployment.yaml
kubectl apply -f k8s/plain/api-service.yaml
kubectl apply -f k8s/batch-cronjob.yaml
kubectl apply -f k8s/drift-cronjob.yaml
kubectl apply -f k8s/retrain-cronjob.yaml
```

### Test
```bash
kubectl -n churn-mlops wait --for=condition=ready pod -l app=churn-api --timeout=180s
kubectl -n churn-mlops port-forward svc/churn-api 8000:8000 &
curl http://localhost:8000/ready
```

---

## Operations Commands

### Manual Retrain
```bash
kubectl -n churn-mlops create job --from=cronjob/churn-retrain-weekly retrain-manual-$(date +%s)
kubectl -n churn-mlops wait --for=condition=complete job/retrain-manual-* --timeout=600s
kubectl -n churn-mlops rollout restart deployment/churn-api
```

### Manual Drift Check
```bash
kubectl -n churn-mlops create job --from=cronjob/churn-drift-weekly drift-manual-$(date +%s)
kubectl -n churn-mlops logs -l job-name=drift-manual-* --tail=200
```

### Scale API
```bash
kubectl -n churn-mlops scale deployment/churn-api --replicas=5
```

### Rollback Deployment
```bash
kubectl -n churn-mlops rollout undo deployment/churn-api
```

### View Logs
```bash
kubectl -n churn-mlops logs -f deployment/churn-api
```

### Clean Up Jobs
```bash
kubectl -n churn-mlops delete jobs --all
```

---

## Summary: V1 Commands Count

| Phase | Commands |
|-------|----------|
| Setup | 8 |
| Local Pipeline | 10 |
| Docker | 4 |
| Minikube | 12 |
| EKS | 15 |
| Operations | 8 |
| **Total** | **57** |
