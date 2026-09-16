FROM python:3.11-slim

WORKDIR /app

COPY mcp-servers/postgres_mcp/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY mcp-servers/postgres_mcp/server.py ./server.py

RUN python -c "from shared.embeddings import embed; embed('warmup')"

EXPOSE 8001

CMD ["python", "server.py"]
