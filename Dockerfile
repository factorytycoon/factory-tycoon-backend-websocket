# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

COPY main.py ./

# 필요시 requirements.txt 사용
# COPY requirements.txt ./
# RUN pip install --no-cache-dir -r requirements.txt

RUN pip install redis python-dotenv fastapi uvicorn
RUN pip install 'uvicorn[standard]'

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
