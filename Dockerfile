# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

COPY redis_stream_reader.py ./

# 필요시 requirements.txt 사용
# COPY requirements.txt ./
# RUN pip install --no-cache-dir -r requirements.txt

RUN pip install redis python-dotenv fastapi uvicorn

CMD ["uvicorn", "redis_stream_reader:app", "--host", "0.0.0.0", "--port", "8000"]
