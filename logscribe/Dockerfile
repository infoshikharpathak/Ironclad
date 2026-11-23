# LogScribe watching Ironclad's logs (docker compose --profile logscribe).
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Pinned by full commit SHA.
RUN pip install --no-cache-dir \
    "logscribe @ git+https://github.com/infoshikharpathak/logscribe.git@c192e686bc506337548d311de567d9f15e2122af"

WORKDIR /config
COPY ironclad.toml seed_incidents.json ./

# Seeding is idempotent (upsert), so it's safe on every start.
CMD ["sh", "-c", "logscribe seed --config /config/ironclad.toml && logscribe watch --config /config/ironclad.toml --report /root/.logscribe/ironclad-report.jsonl"]
