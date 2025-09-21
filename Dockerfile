FROM python:3.12-slim AS runtime

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY neuralmonitor ./neuralmonitor
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "neuralmonitor.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

