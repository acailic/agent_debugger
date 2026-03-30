# Multi-stage Dockerfile for peaky-peek-server
# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# Copy frontend package files
COPY frontend/package.json frontend/package-lock.json* ./

# Install dependencies
RUN npm ci

# Copy frontend source and build
COPY frontend/ ./
RUN npm run build

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Copy package definition
COPY pyproject-server.toml ./

# Copy built frontend from stage 1
COPY --from=frontend-builder /frontend/dist ./frontend/dist

# Copy SDK and server source
COPY agent_debugger_sdk/ ./agent_debugger_sdk/
COPY api/ ./api/
COPY auth/ ./auth/
COPY collector/ ./collector/
COPY redaction/ ./redaction/
COPY storage/ ./storage/

# Install the package
RUN pip install --no-cache-dir -e .

# Create traces directory for data persistence
RUN mkdir -p /app/traces && \
    adduser --disabled-password --gecos '' appuser
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

# Default command
CMD ["peaky-peek", "--host", "0.0.0.0", "--port", "8000"]
