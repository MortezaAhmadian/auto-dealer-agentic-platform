FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# shared/ holds the DB models + embedding helper used by both this app and
# the MCP servers, so it's copied in from the repo root build context.
COPY shared/ ./shared/
COPY backend/app ./app
COPY backend/scripts ./scripts

# Downloads the sentence-transformers model at build time so first request isn't slow
RUN python -c "from shared.embeddings import embed; embed('warmup')"

EXPOSE 8000

CMD ["sh", "-c", "python scripts/init_db.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
