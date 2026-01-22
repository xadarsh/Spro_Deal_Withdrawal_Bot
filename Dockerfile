# Use Python 3.10 slim image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . .

# Set environment variables (these will be overridden by Koyeb)
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "main.py"]
