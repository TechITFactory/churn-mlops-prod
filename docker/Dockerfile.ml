# Stage 1: Builder
FROM python:3.10-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements ./requirements
COPY pyproject.toml README.md ./

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --target=/install \
    -r requirements/base.txt \
    -r requirements/dev.txt && \
    if [ -f requirements/serving.txt ]; then \
      pip install --no-cache-dir --target=/install -r requirements/serving.txt; \
    fi

# Stage 2: Runtime
FROM python:3.10-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    bash \
    && rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Copy Python packages from builder
COPY --from=builder /install /usr/local/lib/python3.10/site-packages

# Copy application code
COPY src ./src
COPY config ./config
COPY scripts ./scripts
COPY pyproject.toml README.md ./

# Make scripts executable
RUN chmod +x ./scripts/*.sh

# Install the package
RUN pip install --no-cache-dir .

# Create necessary directories with proper permissions
RUN mkdir -p /app/data/{raw,processed,features,predictions} \
    /app/artifacts/{models,metrics,reports,registry} && \
    chmod -R 755 /app/data /app/artifacts

# Create non-root user for security
RUN groupadd -r mlops && useradd -r -g mlops mlops && \
    chown -R mlops:mlops /app

USER mlops

# Environment variables
ENV CHURN_MLOPS_CONFIG=/app/config/config.yaml \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import churn_mlops; print('healthy')" || exit 1

# Labels for metadata
ARG BUILD_DATE
ARG VCS_REF
LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.title="Churn MLOps ML" \
      org.opencontainers.image.description="ML training and batch scoring container" \
      org.opencontainers.image.vendor="TechITFactory"

CMD ["bash"]
