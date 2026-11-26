FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn[standard]
COPY *.py clients.json ./
COPY api ./api
COPY prep ./prep
COPY datasets ./datasets
ENV DATA_DIR=/data RUNS_DIR=/app/runs
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
