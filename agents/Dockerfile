FROM python:3.11-slim

WORKDIR /app

COPY agents/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY agents/ ./

# No CMD: this container is meant to be run on demand for cli.py or watch.py,
# e.g. `docker-compose run --rm agents python cli.py`. See docker-compose.yml.
