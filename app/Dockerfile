# Image dung chung cho 2 container: streamlit (Dashboard) va groq-agent (Text-to-SQL)
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common ./common
COPY agent ./agent
COPY dashboard ./dashboard

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1
