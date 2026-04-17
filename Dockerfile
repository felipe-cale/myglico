FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV MYGLICO_RELOAD=1
ENV WATCHFILES_FORCE_POLLING=true

WORKDIR /app

COPY . .
RUN pip install --upgrade pip && pip install .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && python scripts/bootstrap_db.py && if [ \"$MYGLICO_RELOAD\" = \"1\" ]; then exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/app --reload-dir /app/app/templates --reload-dir /app/app/static; else exec uvicorn app.main:app --host 0.0.0.0 --port 8000; fi"]
