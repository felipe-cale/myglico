FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV MYGLICO_RELOAD=1
ENV WATCHFILES_FORCE_POLLING=true

WORKDIR /app

COPY . .
RUN pip install --upgrade pip && pip install ".[full]"

EXPOSE 8001

CMD ["sh", "-c", "alembic upgrade head && python scripts/import_uci_diabetes.py && if [ \"$MYGLICO_RELOAD\" = \"1\" ]; then exec uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload --reload-dir /app/app; else exec uvicorn app.main:app --host 0.0.0.0 --port 8001; fi"]
