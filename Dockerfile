FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py extract_curl_config.py api_server.py ./
COPY web ./web

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "api_server.py", "--host", "0.0.0.0", "--port", "8000"]
