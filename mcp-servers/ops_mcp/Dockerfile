FROM python:3.11-slim

WORKDIR /app

COPY mcp-servers/ops_mcp/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY mcp-servers/ops_mcp/server.py ./server.py

EXPOSE 8002

CMD ["python", "server.py"]
