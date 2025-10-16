# ===========================================
# Base image
# ===========================================
FROM python:3.12-slim

# ===========================================
# Environment setup
# ===========================================
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ===========================================
# Working directory
# ===========================================
WORKDIR /app

# ===========================================
# Install system dependencies
# ===========================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# ===========================================
# Copy backend source
# ===========================================
COPY . /app

# ===========================================
# Install Python dependencies
# ===========================================
RUN pip install --upgrade pip
RUN pip install -r /app/requirements.txt

# ===========================================
# Create persistent folders
# ===========================================
RUN mkdir -p /app/db /app/cache

# ===========================================
# Expose FastAPI port
# ===========================================
EXPOSE 8000

# ===========================================
# Run FastAPI server
# ===========================================
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
