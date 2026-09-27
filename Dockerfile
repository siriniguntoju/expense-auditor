FROM node:22-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY auditor/ auditor/
COPY tools_mcp/ tools_mcp/
COPY data/ data/
COPY --from=web /web/dist web/dist
RUN useradd --create-home auditor && mkdir results && chown auditor:auditor results
USER auditor
CMD ["python", "-m", "uvicorn", "auditor.api:app", "--host", "0.0.0.0", "--port", "5190"]
