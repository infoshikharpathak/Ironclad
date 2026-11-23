FROM python:3.12-slim

WORKDIR /app

# git is needed for pip to fetch the garrison git dependency (and the anvil-ai / agent-forge it pins).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Anvil and agent-forge are installed as packages via requirements.txt
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
