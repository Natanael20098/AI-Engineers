FROM python:3.12-slim

# Security: run as non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Change ownership
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 5000

# Use Gunicorn for production; bind on all interfaces inside the container.
# HTTPS termination is handled by a reverse proxy (nginx / load balancer).
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", \
     "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", \
     "authentication:app"]
