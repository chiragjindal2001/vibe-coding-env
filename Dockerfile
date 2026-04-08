FROM python:3.11-slim

WORKDIR /app

# ── System dependencies ────────────────────────────────────────────────────
# nodejs/npm: needed to run task_3_notes_express (agent writes Express apps)
# Playwright system deps are installed via playwright install --with-deps below
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget curl gnupg \
        nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────────
# Copy only the requirements file first so Docker can cache this layer
COPY server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright browser ─────────────────────────────────────────────────────
RUN playwright install chromium --with-deps

# ── Project source ─────────────────────────────────────────────────────────
# Copy the entire repo so models.py, graders/, tasks/, inference.py are all present
COPY . /app/

# ── Runtime ───────────────────────────────────────────────────────────────
EXPOSE 7860

# OpenEnv API server on 7860; task servers (uvicorn/node/http.server) use 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
