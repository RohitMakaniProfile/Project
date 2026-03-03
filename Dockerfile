FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set PYTHONPATH so alembic and app modules resolve correctly
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Default command: run migrations then start API server
CMD ["bash", "start.sh"]
