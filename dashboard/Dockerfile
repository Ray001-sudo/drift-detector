FROM python:3.11-slim-bookworm AS builder

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

USER 1001

CMD ["uvicorn", "dashboard.main:app", "--host", "0.0.0.0", "--port", "443"]
