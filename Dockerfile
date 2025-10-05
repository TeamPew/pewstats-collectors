FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml .

# Install dependencies from pyproject.toml
RUN pip install --no-cache-dir -e .

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Create user with matching host UID/GID for volume permissions
ARG USER_ID=1001
ARG GROUP_ID=1001
RUN groupadd -g $GROUP_ID appuser && useradd -u $USER_ID -g $GROUP_ID -r appuser

# Create logs directory and set ownership
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set PYTHONPATH to include src directory
ENV PYTHONPATH=/app/src

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "from pewstats_collectors.core.database_manager import DatabaseManager; import os; db = DatabaseManager(host=os.getenv('POSTGRES_HOST', 'localhost'), dbname=os.getenv('POSTGRES_DB', 'pewstats_production'), user=os.getenv('POSTGRES_USER', 'pewstats_prod_user'), password=os.getenv('POSTGRES_PASSWORD', '')); exit(0 if db.ping() else 1)"

# Default command (can be overridden for different workers)
CMD ["python3", "-m", "pewstats_collectors.services.match_discovery_service"]
