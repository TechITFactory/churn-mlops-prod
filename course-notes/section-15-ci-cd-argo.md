# Section 15: CI with GitHub Actions, CD with Argo CD (Docker Hub)

## What You’ll Learn
- Build/test/push churn ML + API images to Docker Hub using GitHub Actions.
- Drive deployments with Argo CD watching this repo (GitOps). 
- Use image tags (git SHA) and a manifest bump step to promote.

## Prereqs
- Docker Hub account (e.g., `techitfactory`).
- GitHub repo with secrets:
  - `DOCKERHUB_USERNAME`
  - `DOCKERHUB_TOKEN` (personal access token or access token with push rights)
  - Optional if pushing a manifest commit: `GH_TOKEN` with repo write.
- EKS cluster reachable by Argo CD (already running). Argo CD will pull manifests; Actions does **not** need kubeconfig.

## CI: GitHub Actions (Docker Hub)
Create `.github/workflows/ci-cd.yml` (one job for lint/test, one for image build/push). Adjust versions as needed.

```yaml
name: ci-cd
on:
  pull_request:
  push:
    branches: [ main ]
    tags: [ "v*" ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements/dev.txt
      - name: Lint and test
        run: |
          make lint
          make test

  build-and-push:
    needs: test
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Docker meta (tags)
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: |
            techitfactory/churn-ml
            techitfactory/churn-api
          tags: |
            type=ref,event=branch
            type=ref,event=tag
            type=sha
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - name: Build and push churn-ml
        uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/Dockerfile.ml
          push: true
          tags: techitfactory/churn-ml:${{ steps.meta.outputs.version }}
      - name: Build and push churn-api
        uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/Dockerfile.api
          push: true
          tags: techitfactory/churn-api:${{ steps.meta.outputs.version }}
```

Notes:
- `docker/metadata-action` generates tags including the git SHA; Argo should deploy SHA tags (immutable). You can also add a `latest` tag if desired.
- Keep tests in the `test` job so broken code does not ship images.

## Bumping Manifests for Argo CD
Argo CD syncs when manifests change. Two options:
1) **Manual**: You edit `k8s/api-deployment.yaml` (and any CronJobs that use the images) to the new tag and push. Argo syncs.
2) **Automated**: Add a small step after image push to update image tags and commit to `main` (or a deploy branch). Example using `yq` and `GH_TOKEN` with repo write.

Pseudo-step to add after builds (not included above):
```bash
TAG=$(git rev-parse --short HEAD)
# Update API deployment
yq -i '(.spec.template.spec.containers[] | select(.name=="churn-api").image) = "techitfactory/churn-api:'"$TAG"'"' k8s/api-deployment.yaml
# Update batch/other jobs if needed
# yq -i '... same pattern ...' k8s/batch-cronjob.yaml

git config user.name "gha-bot"
git config user.email "gha-bot@users.noreply.github.com"
git add k8s/api-deployment.yaml k8s/batch-cronjob.yaml k8s/drift-cronjob.yaml k8s/retrain-cronjob.yaml
git commit -m "chore: deploy tag $TAG" || exit 0
git push origin main
```
(You would add this as an extra step in `build-and-push`, gated to `push` events.)

## CD: Argo CD Setup (once per cluster)
1) Install Argo CD (default, in namespace `argocd`):
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```
2) Port-forward UI:
```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
```
3) Get initial admin password:
```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```
4) Login via UI or CLI (`argocd login localhost:8080 --username admin --password <pwd>`), then change the password.

## Argo CD Application (GitOps)
Create an Application that points to this repo and the `k8s/` directory (root manifests). Save as `argocd/app-churn-mlops.yaml` and apply.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: churn-mlops
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/<your-org>/techitfactory-churn-mlops.git
    targetRevision: main
    path: k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: churn-mlops
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```
Apply:
```bash
kubectl apply -f argocd/app-churn-mlops.yaml
```
Argo CD will now watch `k8s/` on `main` and sync changes (including image tag bumps).

## Promotion Flow (Recommended)
- Build once → push image with SHA tag.
- Bump manifest image tag to that SHA in `k8s/` (manually or automated step) → commit to `main`.
- Argo syncs and deploys. For staging/prod, use separate overlays/Applications pointing to different paths/branches and require manual sync in prod.

## What to Monitor
- Argo app health: `argocd app get churn-mlops`
- Sync status: UI or CLI; investigate diffs if OutOfSync.
- CI results: GitHub Actions runs on PRs and main; no deploy if tests fail.

## Future Enhancements
- Use Argo Rollouts for canary/blue-green.
- Use SOPS/SealedSecrets/External Secrets for secrets management.
- Add policy checks (kubeconform/OPA) in CI before manifest bumps.
- Split environments with kustomize overlays and separate Argo Applications.
