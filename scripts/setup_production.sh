#!/bin/bash
# Production Setup Script
# This script sets up the entire production environment

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="${REPO_URL:-https://github.com/yourusername/churn-mlops-prod.git}"
GITHUB_ORG="${GITHUB_ORG:-yourusername}"
DOMAIN="${DOMAIN:-example.com}"
EMAIL="${EMAIL:-admin@example.com}"

echo -e "${GREEN}=== Churn MLOps Production Setup ===${NC}"
echo ""

# Check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"
    
    local missing_tools=()
    
    command -v kubectl >/dev/null 2>&1 || missing_tools+=("kubectl")
    command -v helm >/dev/null 2>&1 || missing_tools+=("helm")
    command -v argocd >/dev/null 2>&1 || missing_tools+=("argocd")
    command -v docker >/dev/null 2>&1 || missing_tools+=("docker")
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        echo -e "${RED}Missing required tools: ${missing_tools[*]}${NC}"
        echo "Please install them and try again."
        exit 1
    fi
    
    echo -e "${GREEN}✓ All prerequisites met${NC}"
}

# Setup Kubernetes cluster
setup_cluster() {
    echo -e "${YELLOW}Setting up Kubernetes cluster components...${NC}"
    
    # Install ingress controller
    echo "Installing ingress-nginx..."
    helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
    helm repo update
    
    if ! helm list -n ingress-nginx | grep -q ingress-nginx; then
        helm install ingress-nginx ingress-nginx/ingress-nginx \
            --namespace ingress-nginx \
            --create-namespace \
            --set controller.metrics.enabled=true \
            --set controller.podAnnotations."prometheus\.io/scrape"=true \
            --set controller.podAnnotations."prometheus\.io/port"=10254
    fi
    
    # Install cert-manager
    echo "Installing cert-manager..."
    kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
    
    # Wait for cert-manager to be ready
    kubectl wait --for=condition=Ready pods --all -n cert-manager --timeout=300s
    
    # Create ClusterIssuer
    echo "Creating Let's Encrypt ClusterIssuer..."
    kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ${EMAIL}
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
    
    echo -e "${GREEN}✓ Cluster components installed${NC}"
}

# Install ArgoCD
install_argocd() {
    echo -e "${YELLOW}Installing ArgoCD...${NC}"
    
    kubectl create namespace argocd || true
    kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
    
    # Wait for ArgoCD to be ready
    kubectl wait --for=condition=Ready pods --all -n argocd --timeout=600s
    
    # Get ArgoCD password
    ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
    
    echo -e "${GREEN}✓ ArgoCD installed${NC}"
    echo -e "${YELLOW}ArgoCD initial admin password retrieved (not printed).${NC}"
    echo "If you need to view it, run (avoid shared terminals/logging):"
    echo '  kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d'
    
    # Port forward for initial setup
    echo "Starting port-forward on localhost:8080..."
    kubectl port-forward svc/argocd-server -n argocd 8080:443 > /dev/null 2>&1 &
    PF_PID=$!
    sleep 5
    
    # Login to ArgoCD
    argocd login localhost:8080 --username admin --password "${ARGOCD_PASSWORD}" --insecure
    
    # Change password (optional)
    echo "You should change the admin password:"
    echo "  argocd account update-password"
    
    # Kill port-forward
    kill $PF_PID || true
    
    echo -e "${GREEN}✓ ArgoCD configured${NC}"
}

# Setup namespaces and secrets
setup_namespaces() {
    echo -e "${YELLOW}Setting up namespaces...${NC}"
    
    # Create namespaces
    kubectl create namespace churn-mlops-staging || true
    kubectl create namespace churn-mlops-production || true
    
    # Prompt for GitHub token
    echo "Enter your GitHub Personal Access Token (for pulling images):"
    read -s GITHUB_TOKEN
    
    if [ -n "$GITHUB_TOKEN" ]; then
        # Create image pull secrets
        kubectl create secret docker-registry ghcr-secret \
            --docker-server=ghcr.io \
            --docker-username="${GITHUB_ORG}" \
            --docker-password="${GITHUB_TOKEN}" \
            -n churn-mlops-staging \
            --dry-run=client -o yaml | kubectl apply -f -
        
        kubectl create secret docker-registry ghcr-secret \
            --docker-server=ghcr.io \
            --docker-username="${GITHUB_ORG}" \
            --docker-password="${GITHUB_TOKEN}" \
            -n churn-mlops-production \
            --dry-run=client -o yaml | kubectl apply -f -
        
        echo -e "${GREEN}✓ Image pull secrets created${NC}"
    fi
}

# Deploy ArgoCD applications
deploy_applications() {
    echo -e "${YELLOW}Deploying ArgoCD applications...${NC}"
    
    # Update repository URLs in ArgoCD manifests
    find argocd/ -name "*.yaml" -exec sed -i "s|yourusername|${GITHUB_ORG}|g" {} \;
    
    # Deploy AppProject
    kubectl apply -f argocd/appproject.yaml
    
    # Deploy staging
    kubectl apply -f argocd/staging/application.yaml
    
    echo "Waiting for staging to sync..."
    argocd app wait churn-mlops-staging --timeout 600
    
    # Ask before deploying production
    echo ""
    echo -e "${YELLOW}Deploy to production? (y/N)${NC}"
    read -r DEPLOY_PROD
    
    if [[ "$DEPLOY_PROD" =~ ^[Yy]$ ]]; then
        kubectl apply -f argocd/production/application.yaml
        echo "Waiting for production to sync..."
        argocd app wait churn-mlops-production --timeout 600
    fi
    
    echo -e "${GREEN}✓ Applications deployed${NC}"
}

# Install monitoring (optional)
install_monitoring() {
    echo ""
    echo -e "${YELLOW}Install Prometheus & Grafana? (y/N)${NC}"
    read -r INSTALL_MON
    
    if [[ "$INSTALL_MON" =~ ^[Yy]$ ]]; then
        echo "Installing kube-prometheus-stack..."
        helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
        helm repo update
        
        helm install prometheus prometheus-community/kube-prometheus-stack \
            --namespace monitoring \
            --create-namespace \
            --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false
        
        echo -e "${GREEN}✓ Monitoring installed${NC}"
        echo "Access Grafana:"
        echo "  kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80"
        echo "  Username: admin"
        echo "  Password: (retrieve via kubectl)"
        echo '    kubectl get secret -n monitoring prometheus-grafana -o jsonpath="{.data.admin-password}" | base64 -d'
    fi
}

# Print summary
print_summary() {
    echo ""
    echo -e "${GREEN}=== Setup Complete ===${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Access ArgoCD UI:"
    echo "   kubectl port-forward svc/argocd-server -n argocd 8080:443"
    echo "   Open: https://localhost:8080"
    echo ""
    echo "2. Check application status:"
    echo "   argocd app list"
    echo "   argocd app get churn-mlops-staging"
    echo ""
    echo "3. Access staging API:"
    echo "   kubectl port-forward -n churn-mlops-staging svc/churn-mlops-api 8000:8000"
    echo "   Test: curl http://localhost:8000/health"
    echo ""
    echo "4. Configure DNS records:"
    echo "   - churn-api-staging.${DOMAIN} -> Load Balancer IP"
    echo "   - churn-api.${DOMAIN} -> Load Balancer IP"
    echo ""
    echo "5. Review documentation:"
    echo "   - docs/PRODUCTION_DEPLOYMENT.md"
    echo "   - docs/GITOPS_WORKFLOW.md"
    echo "   - argocd/README.md"
    echo ""
    
    # Get LoadBalancer IP
    LB_IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "pending")
    echo "Ingress LoadBalancer IP: ${LB_IP}"
}

# Main execution
main() {
    check_prerequisites
    setup_cluster
    install_argocd
    setup_namespaces
    deploy_applications
    install_monitoring
    print_summary
}

# Run main function
main
