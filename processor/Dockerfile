FROM python:3.11-slim-bookworm AS builder

# Install build deps for rocksdict or faust-streaming
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

RUN useradd -u 1001 appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim-bookworm

RUN useradd -u 1001 appuser
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

# Create rocksdb data dir and chown
RUN mkdir -p /app/rocksdb_data && chown -R 1001:1001 /app/rocksdb_data

USER 1001

CMD ["faust", "-A", "processor.main", "worker", "-l", "info"]
