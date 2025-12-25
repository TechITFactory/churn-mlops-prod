cd terraform
terraform apply
aws eks update-kubeconfig --name churn-mlops --region us-east-1
kubectl get nodes


kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd port-forward svc/argocd-server 8080:443
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
argocd login localhost:8080 --username admin --password <pwd>
kubectl apply -n argocd -f argocd/app-churn-mlops.yaml

kubectl -n argocd get applications
kubectl -n churn-mlops get deploy,cronjob,svc,pvc

# What to run locally (Docker Compose demo)

Seed/train once (creates production_latest.joblib):
docker compose run --rm seed-model

Start the stack (API + Prometheus + Grafana):
docker compose up --build
Where “churn-ml” is now

seed-model (one-off): runs the full pipeline scripts and exits.
churn-ml (interactive): lets you run drift/retrain manually anytime:
docker compose run --rm churn-ml python -m churn_mlops.monitoring.run_drift_check
docker compose run --rm churn-ml python -m churn_mlops.training.train_candidate
docker compose run --rm churn-ml python -m churn_mlops.training.promote_model
Verification

API: http://localhost:8000/ready should be OK after seeding
Prometheus: http://localhost:9090 → query rate(churn_api_requests_total[5m])
Grafana: http://localhost:3000 (admin/admin), Prometheus datasource is pre-wired
Grafana: http://localhost:3000 (Username: admin, Password: set via env/secret)
	- If running in K8s (kube-prometheus-stack):
		kubectl get secret -n monitoring prometheus-grafana -o jsonpath="{.data.admin-password}" | base64 -d
	- If running via docker compose: set GRAFANA_ADMIN_PASSWORD (see .env.example)
If you want, I can add a tiny “demo script” (single command) that runs seed + starts compose + prints the URLs.

kubectl create job -n churn-mlops --from=cronjob/churn-drift-daily churn-drift-manual