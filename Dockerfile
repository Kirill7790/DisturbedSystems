# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

WORKDIR /build

# Системні залежності тільки для етапу збірки
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install -r requirements.txt


FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY . .

EXPOSE 8000

CMD ["waitress-serve", "--call", "--threads=64", "--port=8000", "app:create_app"]