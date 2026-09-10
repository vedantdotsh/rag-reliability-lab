FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY data ./data
COPY config ./config
COPY dashboard/dist ./dashboard/dist

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["rag-eval"]
CMD ["evaluate", "--gate"]
