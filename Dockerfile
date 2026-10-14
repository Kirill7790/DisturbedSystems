FROM python:3.12-slim

WORKDIR /app

# Системні залежності для psycopg (потрібен libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Встановлення залежностей для додатку (requirements.txt)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Імпорт коду
COPY . .

EXPOSE 8000

CMD ["waitress-serve", "--call", "--threads=16", "--port=8000", "app:create_app"]