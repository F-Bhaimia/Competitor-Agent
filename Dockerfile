# Competitor News Monitor - Docker Image
FROM python:3.11-slim-bookworm

# Install system dependencies for Playwright and WeasyPrint
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core utilities
    curl git \
    # Playwright browser dependencies
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libatspi2.0-0 \
    # WeasyPrint/PDF dependencies
    libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
    libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/competitor-agent

# Install Python dependencies first (for layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium && playwright install-deps chromium

# Copy application code
COPY . .

# Create directories for data persistence
RUN mkdir -p data logs exports config

# Add application to Python path
ENV PYTHONPATH=/opt/competitor-agent

# Expose ports
EXPOSE 8501 8001

# Default command (can be overridden in docker-compose)
CMD ["streamlit", "run", "streamlit_app/Home.py", "--server.port=8501", "--server.address=0.0.0.0"]
