FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY contractforge/ ./contractforge/
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home app && mkdir /data && chown app:app /data
USER app
ENV DB_PATH=/data/contractforge.db
EXPOSE 8012
CMD ["python", "-m", "uvicorn", "contractforge.api:app", "--host", "0.0.0.0", "--port", "8012"]
