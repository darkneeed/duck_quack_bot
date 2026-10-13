FROM python:3.12-slim

WORKDIR /app

# 1. Create non-root user and persistent directories before code layers
RUN useradd -u 1000 -m -U botuser && \
    mkdir -p /app/data && \
    chown -R botuser:botuser /app

# 2. Dependencies with BuildKit cache mount
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# 3. Application source with direct non-root ownership (no duplicate chown layer)
COPY --chown=botuser:botuser . .

USER botuser

CMD ["python", "-m", "s21_bot.main"]
