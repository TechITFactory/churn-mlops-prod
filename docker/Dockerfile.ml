FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

COPY requirements ./requirements
COPY pyproject.toml ./
COPY README.md ./
COPY config ./config

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements/runtime.txt

COPY src ./src

RUN pip install --no-cache-dir .

ENV CHURN_MLOPS_CONFIG=/app/config/config.yaml

CMD ["python", "-c", "print('Use: python -m churn_mlops.training.train_baseline | train_candidate | promote_model | churn_mlops.inference.batch_score')"]
