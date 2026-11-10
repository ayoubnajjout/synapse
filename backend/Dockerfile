FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LITELLM_TELEMETRY=False LITELLM_LOCAL_MODEL_COST_MAP=True
WORKDIR /app
COPY backend/requirements.lock ./requirements.lock
RUN --mount=type=cache,target=/root/.cache/pip pip install --retries 5 --timeout 60 -r requirements.lock \
    && useradd --create-home --uid 10001 synapse
COPY --chown=synapse:synapse backend/app ./app
USER synapse
ENV SYNAPSE_CONTAINER=1
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=70s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
