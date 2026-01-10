# Dockerfile for KB-Standalone Backend

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy backend files
COPY backend/ .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-render-minimal.txt

# Create static directory for visualizations
RUN mkdir -p static/visualizations

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
