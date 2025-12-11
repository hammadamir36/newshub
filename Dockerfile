FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY requirements.txt .

# Copy templates folder
COPY templates/ ./templates/

# Verify files are copied
RUN echo "=== Files in /app ===" && ls -la /app/
RUN echo "=== Files in /app/templates ===" && ls -la /app/templates/

# Expose port
EXPOSE 7860

# Set environment variables
ENV PORT=7860
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "app.py"]