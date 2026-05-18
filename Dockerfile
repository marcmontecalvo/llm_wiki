# Stage 1: builder
FROM python:3.11-slim AS builder
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock LICENSE README.md ./
COPY src/ ./src/
RUN uv sync --frozen

# Stage 2: runtime
FROM python:3.11-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends supervisor curl \
    && rm -rf /var/lib/apt/lists/*
RUN adduser --disabled-password --uid 1000 --gecos "" llmwiki
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . /app/
COPY supervisord.conf /app/supervisord.conf
COPY entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh && mkdir -p /var/log/llm-wiki /app/wiki_system/logs /var/run /app/config && chown -R llmwiki:llmwiki /var/log/llm-wiki /app/wiki_system /var/run /app/config
ENV PATH="/app/.venv/bin:$PATH"
ENV WIKI_ROOT=/wiki
ENV WIKI_PORT=3050
EXPOSE 3050
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD curl -sf http://localhost:${WIKI_PORT:-3050}/v1/health | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('daemon_running') else 1)" || exit 1
USER llmwiki
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["supervisord", "-c", "/app/supervisord.conf"]
