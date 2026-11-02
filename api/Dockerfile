# Build context is the repo root (the image needs both agent/ and api/).
FROM python:3.12-slim AS build
RUN pip install --no-cache-dir uv==0.9.5
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
COPY pyproject.toml uv.lock .python-version ./
COPY agent/pyproject.toml agent/README.md agent/
COPY api/pyproject.toml api/README.md api/
# Dependencies first, so code changes don't invalidate this layer.
RUN uv sync --frozen --no-dev --package smartspend-api --no-install-workspace
COPY agent/smartspend_agent agent/smartspend_agent
COPY api/smartspend_api api/smartspend_api
RUN uv sync --frozen --no-dev --package smartspend-api --no-editable

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PORT=8080
USER app
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn smartspend_api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
