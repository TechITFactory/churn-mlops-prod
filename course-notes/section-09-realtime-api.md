# Section 09: Real-time Prediction API

## Goal

Build a production-ready FastAPI service that serves real-time churn predictions with health checks, Prometheus metrics, and proper error handling.

---

## API Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                   │
├─────────────────────────────────────────────────────────┤
│  /predict         → Churn risk for single user          │
│  /health          → Backward-compatible health check     │
│  /live            → Liveness probe (always OK)          │
│  /ready           → Readiness probe (model loaded?)     │
│  /metrics         → Prometheus metrics                   │
└─────────────────────────────────────────────────────────┘
            ↓
    Model: production_latest.joblib
```

---

## File: `src/churn_mlops/api/app.py`

### FastAPI Application

```python
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

app = FastAPI(title="TechITFactory Churn API", version="0.1.0")

# Add metrics middleware
app.middleware("http")(metrics_middleware())
```

---

## Endpoints

### 1. Prediction: `POST /predict`

**Request**:
```json
{
  "user_id": "12345",
  "snapshot_date": "2025-01-15",
  "features": {
    "active_days_7d": 3,
    "active_days_14d": 5,
    "active_days_30d": 12,
    "events_7d": 25,
    "watch_minutes_7d": 120.5,
    "watch_minutes_14d": 250.0,
    "watch_minutes_30d": 600.0,
    "quiz_attempts_7d": 2,
    "quiz_avg_score_7d": 85.0,
    "days_since_last_activity": 0,
    "days_since_signup": 45,
    "payment_fail_rate_30d": 0.0,
    "plan": "paid",
    "is_paid": 1,
    "country": "US",
    "marketing_source": "organic"
  }
}
```

**Response**:
```json
{
  "user_id": "12345",
  "churn_risk": 0.23,
  "model_path": "/app/artifacts/models/production_latest.joblib"
}
```

**Implementation**:
```python
@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    if _model is None:
        _load_model_or_raise(cfg)
    
    # Convert feature dict → DataFrame
    x = pd.DataFrame([req.features])
    
    # Predict probability of churn (class 1)
    proba = float(_model.predict_proba(x)[:, 1])
    
    # Increment Prometheus counter
    PREDICTION_COUNT.inc()
    
    return PredictResponse(
        user_id=req.user_id,
        churn_risk=proba,
        model_path=str(_production_model_path(cfg))
    )
```

---

### 2. Health: `GET /health`

**Purpose**: Backward-compatible health check (calls `/ready`)

**Response**:
```json
{
  "status": "ready",
  "model": "/app/artifacts/models/production_latest.joblib"
}
```

---

### 3. Liveness: `GET /live`

**Purpose**: Kubernetes liveness probe (is process alive?)

**Response**:
```json
{
  "status": "live"
}
```

**Always returns 200** unless the process crashes

---

### 4. Readiness: `GET /ready`

**Purpose**: Kubernetes readiness probe (is model loaded?)

**Response** (success):
```json
{
  "status": "ready",
  "model": "/app/artifacts/models/production_latest.joblib"
}
```

**Response** (failure):
```json
{
  "detail": "Missing production model alias: ..."
}
```
**HTTP 500** if model not loaded

**Implementation**:
```python
@app.get("/ready")
def ready():
    try:
        if _model is None:
            _load_model_or_raise(cfg)
        return {"status": "ready", "model": _model_meta.get("model_path")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

### 5. Metrics: `GET /metrics`

**Purpose**: Prometheus metrics scraping

**Response** (plain text):
```
# HELP churn_api_requests_total Total HTTP requests
# TYPE churn_api_requests_total counter
churn_api_requests_total{method="POST",path="/predict",status="200"} 1523.0

# HELP churn_api_request_latency_seconds Request latency in seconds
# TYPE churn_api_request_latency_seconds histogram
churn_api_request_latency_seconds_bucket{method="POST",path="/predict",le="0.005"} 1200.0

# HELP churn_api_predictions_total Total predictions served
# TYPE churn_api_predictions_total counter
churn_api_predictions_total 1523.0
```

**Implementation**:
```python
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

@app.get("/metrics")
def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
```

---

## Prometheus Metrics

### File: `src/churn_mlops/monitoring/api_metrics.py`

**Metrics Defined**:

1. **REQUEST_COUNT**: Total HTTP requests by method/path/status
   ```python
   Counter("churn_api_requests_total", "Total HTTP requests",
           ["method", "path", "status"])
   ```

2. **REQUEST_LATENCY**: Request latency histogram
   ```python
   Histogram("churn_api_request_latency_seconds", "Request latency",
             ["method", "path"])
   ```

3. **PREDICTION_COUNT**: Total predictions served
   ```python
   Counter("churn_api_predictions_total", "Total predictions served")
   ```

---

## Metrics Middleware

```python
def metrics_middleware():
    async def middleware(request, call_next):
        start = time.perf_counter()
        status_code = 500
        
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            path = request.url.path
            method = request.method
            
            REQUEST_LATENCY.labels(method=method, path=path).observe(elapsed)
            REQUEST_COUNT.labels(method=method, path=path, status=str(status_code)).inc()
    
    return middleware
```

**Automatic tracking**:
- Every request increments counters
- Latency tracked per endpoint
- No manual instrumentation needed in handlers

---

## Model Loading

### Startup Event

```python
@app.on_event("startup")
def startup_event():
    cfg = _get_config()
    try:
        _load_model_or_raise(cfg)
    except Exception as e:
        # Don't crash process (allow /live to succeed)
        # But /ready will fail until model loaded
        _model_meta = {"startup_error": str(e)}
```

**Why not crash on startup?**
- Allows pod to start (Kubernetes won't kill it immediately)
- `/live` probe succeeds (process is running)
- `/ready` probe fails (pod doesn't receive traffic)
- Gives time to debug (check logs, fix PVC mount, etc.)

---

## Files Involved

| File | Purpose |
|------|---------|
| `src/churn_mlops/api/app.py` | FastAPI application |
| `src/churn_mlops/monitoring/api_metrics.py` | Prometheus metrics |
| `scripts/run_api.sh` | Local API startup script |
| `docker/Dockerfile.api` | API Docker image |
| `k8s/api-deployment.yaml` | Kubernetes Deployment |
| `k8s/api-service.yaml` | Kubernetes Service |
| `artifacts/models/production_latest.joblib` | Production model (input) |

---

## Run Commands

### Local Development

```bash
# Set config
export CHURN_MLOPS_CONFIG=./config/config.yaml

# Run with uvicorn
uvicorn churn_mlops.api.app:app --host 0.0.0.0 --port 8000

# Or use script
./scripts/run_api.sh

# In another terminal, test
curl http://localhost:8000/health
curl http://localhost:8000/metrics
```

### Docker

```bash
# Build image
docker build -t techitfactory/churn-api:0.1.0 -f docker/Dockerfile.api .

# Run container
docker run --rm -p 8000:8000 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/artifacts:/app/artifacts \
  techitfactory/churn-api:0.1.0
```

### Kubernetes

```bash
# Deploy
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml

# Port-forward
kubectl -n churn-mlops port-forward svc/churn-api 8000:8000

# Test
curl http://localhost:8000/ready
```

---

## Verify Steps

```bash
# 1. Health check
curl -s http://localhost:8000/health | jq

# 2. Liveness
curl -s http://localhost:8000/live | jq

# 3. Readiness
curl -s http://localhost:8000/ready | jq

# 4. Metrics
curl -s http://localhost:8000/metrics | grep churn_api

# 5. Prediction (example)
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "features": {
      "active_days_7d": 3,
      "watch_minutes_7d": 120,
      "days_since_last_activity": 0,
      "plan": "paid"
    }
  }' | jq
```

---

## Kubernetes Probes

**File**: `k8s/api-deployment.yaml`

```yaml
livenessProbe:
  httpGet:
    path: /live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 20

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

**Why separate liveness and readiness?**
- **Liveness**: "Is the process stuck?" → Restart pod if failing
- **Readiness**: "Is the service ready to handle traffic?" → Remove from load balancer if failing

**Common issue**: Model not loaded → readiness fails → pod never receives traffic → safe!

---

## Error Handling

### Model Not Loaded

```python
@app.post("/predict")
def predict(req: PredictRequest):
    try:
        if _model is None:
            _load_model_or_raise(cfg)
        # ... predict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**Response**:
```json
{
  "detail": "Missing production model alias: ..."
}
```
**HTTP 400**

### Invalid Features

```python
# Pydantic validation (automatic)
class PredictRequest(BaseModel):
    user_id: str = Field(..., description="Unique user id")
    features: Dict[str, float] = Field(..., description="Feature map")
```

**If user sends invalid JSON**:
```json
{
  "detail": [
    {
      "loc": ["body", "features"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```
**HTTP 422** (Unprocessable Entity)

---

## Performance

### Latency Targets

- **P50**: < 50ms
- **P95**: < 100ms
- **P99**: < 200ms

**Measured via**:
```bash
# Prometheus query
histogram_quantile(0.95, rate(churn_api_request_latency_seconds_bucket[5m]))
```

### Load Testing

```bash
# Install locust or ab
pip install locust

# Load test script
locust -f tests/load_test.py --host http://localhost:8000 --users 100 --spawn-rate 10
```

**Bottlenecks**:
- Model prediction (CPU-bound)
- Feature preprocessing (pandas overhead)

**Optimizations**:
- Use ONNX runtime for faster inference
- Batch predictions (accept multiple users in single request)
- Horizontal scaling (increase replicas)

---

## Monitoring & Observability

### Prometheus Scraping

**File**: `k8s/api-metrics-annotations-patch.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: churn-api
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/metrics"
```

### Grafana Dashboard (Example Queries)

```promql
# Request rate
rate(churn_api_requests_total[5m])

# Error rate
rate(churn_api_requests_total{status=~"5.."}[5m])

# Latency P95
histogram_quantile(0.95, rate(churn_api_request_latency_seconds_bucket[5m]))

# Prediction throughput
rate(churn_api_predictions_total[5m])
```

---

## Security Considerations

### 1. Input Validation

- Pydantic schemas enforce types
- Add business logic validation (e.g., `churn_risk` must be [0, 1])

### 2. Rate Limiting (Future)

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/predict")
@limiter.limit("100/minute")
def predict(req: PredictRequest):
    ...
```

### 3. Authentication (Future)

```python
from fastapi.security import HTTPBearer

security = HTTPBearer()

@app.post("/predict")
def predict(req: PredictRequest, token: str = Depends(security)):
    validate_token(token)
    ...
```

---

## Troubleshooting

**Issue**: API returns 500 on startup
- **Cause**: Model not found or config path wrong
- **Fix**: Check `CHURN_MLOPS_CONFIG` env var, ensure `production_latest.joblib` exists

**Issue**: `/ready` probe fails indefinitely
- **Cause**: Model file missing or corrupted
- **Fix**: Check pod logs (`kubectl logs`), verify PVC mount

**Issue**: Predictions always return 0.5
- **Cause**: Model not loaded or using wrong model
- **Fix**: Reload model, check `_model_meta` in `/ready` response

**Issue**: High latency (> 500ms per request)
- **Cause**: Large feature set or complex model
- **Fix**: Profile with `cProfile`, optimize preprocessing, or use ONNX

**Issue**: Metrics not appearing in Prometheus
- **Cause**: Scrape annotations missing or wrong port
- **Fix**: Verify ServiceMonitor or scrape config, check `/metrics` endpoint manually

---

## Best Practices

1. **Separate liveness and readiness**: Don't restart pods just because model not loaded
2. **Use Pydantic**: Schema validation for free
3. **Instrument everything**: Metrics, logs, traces (OpenTelemetry)
4. **Graceful degradation**: Return cached prediction if model fails
5. **Version API**: `/v1/predict`, `/v2/predict` for breaking changes

---

## Next Steps

- **[Section 10](section-10-ci-cd-quality.md)**: CI/CD and code quality
- **[Section 11](section-11-containerization-deploy.md)**: Docker and Kubernetes deployment
- **[Section 12](section-12-monitoring-retrain.md)**: Monitoring and automated retraining

---

## Key Takeaways

1. **FastAPI** provides automatic schema validation and OpenAPI docs
2. **Health checks** (liveness + readiness) enable safe Kubernetes deployments
3. **Prometheus metrics** enable monitoring and alerting
4. **Startup event** loads model once, not per request
5. **Error handling** returns meaningful HTTP status codes and messages
