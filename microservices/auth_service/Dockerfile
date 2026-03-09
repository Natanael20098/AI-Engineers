FROM python:3.12-slim

# Security: run as non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source as a Python package named auth_service so that
# relative imports (from .config import …) resolve correctly at runtime.
COPY . ./auth_service/

# Change ownership to the non-root user
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 5000

# Environment variable defaults (override via docker-compose / .env)
ENV FLASK_ENV=production \
    AUTH_SERVICE_HOST=0.0.0.0 \
    AUTH_SERVICE_PORT=5000

# Use Gunicorn for production; TLS termination is handled by a reverse proxy.
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", \
     "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", \
     "auth_service.main:app"]
