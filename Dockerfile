FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Copy application code
COPY taskflow/ ./taskflow/

# Create non-root user
RUN useradd -m -u 1000 taskflow && chown -R taskflow:taskflow /app
USER taskflow

# Expose port
EXPOSE 8000

# Default command (can be overridden)
CMD ["uvicorn", "taskflow.main:app", "--host", "0.0.0.0", "--port", "8000"]
