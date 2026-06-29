# Dockerfile — for Railway / Docker-based deployments
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY bot.py scanner.py binance_api.py config.py state.py ./

# Create directory for state persistence
RUN mkdir -p /data
ENV STATE_DIR=/data

# Run the bot
CMD ["python", "bot.py"]
