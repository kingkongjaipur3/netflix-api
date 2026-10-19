FROM python:3.10-slim

# सिस्टम डिपेंडेंसी इंस्टॉल करो
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libnss3 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright और Chromium इंस्टॉल करो
RUN playwright install chromium

COPY . .

# Gunicorn चलाओ
CMD gunicorn --bind 0.0.0.0:$PORT app:app
