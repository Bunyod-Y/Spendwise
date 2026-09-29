FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./

RUN useradd --uid 1000 --create-home bot \
    && mkdir -p /data \
    && chown bot:bot /data
USER bot
VOLUME /data

CMD ["python", "main.py"]
