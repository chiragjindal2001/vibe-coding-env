FROM python:3.11-slim

WORKDIR /app

# ── System dependencies ────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends wget curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Make 'python' available (slim image only has python3 by default)
RUN ln -sf /usr/bin/python3 /usr/bin/python

# ── Python dependencies ────────────────────────────────────────────────────
COPY server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright browser ─────────────────────────────────────────────────────
RUN playwright install chromium --with-deps

# ── Project source ─────────────────────────────────────────────────────────
COPY . /app/

# ── Runtime ───────────────────────────────────────────────────────────────
EXPOSE 7860

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]