# Use lightweight Python image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Prevent Python from writing bytecode files
ENV PYTHONDONTWRITEBYTECODE=1

# Ensure logs are displayed immediately
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Railway provides the PORT environment variable
EXPOSE 8000

# Start FastAPI
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]