# Image commune API + worker (architecture §9). Construite depuis le dossier backend/.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY database /database
ENV MIGRATIONS_DIR=/database/migrations SEEDS_DIR=/database/seeds

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "python -m app.db.migrate && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
