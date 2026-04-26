FROM python:3.11-slim AS base
WORKDIR /app
RUN pip install uv
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# ── ingest / seed ────────────────────────────────────────────────────────────
FROM base AS ingest
COPY ingestion/ ./ingestion/
COPY graph/ ./graph/
COPY shared/ ./shared/
COPY ingest.py .
COPY seed.py .
CMD ["python", "ingest.py"]

# ── streamlit app ────────────────────────────────────────────────────────────
FROM base AS app
COPY graph/ ./graph/
COPY shared/ ./shared/
COPY ingestion/ ./ingestion/
COPY app/ ./app/
COPY .streamlit/ ./.streamlit/
EXPOSE 8501
CMD ["streamlit", "run", "app/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
