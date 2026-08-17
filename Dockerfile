FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    HEADLESS=1 \
    NO_HEADLESS=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    wget gnupg2 \
    libnss3 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 libxdamage1 \
    libxi6 libxtst6 libxrandr2 libasound2 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libgbm1 libpangocairo-1.0-0 libpango-1.0-0 \
    libxshmfence1 fonts-liberation fonts-dejavu-core fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    (dpkg -i /tmp/chrome.deb || true) && \
    apt-get update && apt-get install -f -y && \
    rm -f /tmp/chrome.deb && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000
CMD ["sh", "-c", "Xvfb :99 -screen 0 1366x768x24 &>/dev/null & export DISPLAY=:99 && gunicorn turnstile_api:app --workers 1 --threads 2 --timeout 300 --bind 0.0.0.0:${PORT:-10000}"]
