# syntax=docker/dockerfile:1
# Use ARM64 Python for 64-bit Raspberry Pi
FROM arm64v8/python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install minimal dependencies - only what exists in Debian Trixie
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       libgl1 \
       libglib2.0-0t64 \
       v4l-utils \
       libcap-dev \
    && usermod -a -G video root \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DJANGO_SETTINGS_MODULE=TF.settings

EXPOSE 5000

CMD ["daphne", "-b", "0.0.0.0", "-p", "5000", "TF.asgi:application"]
