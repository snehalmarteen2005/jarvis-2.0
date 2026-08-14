FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create the SQLite database directory (needs write permissions)
RUN mkdir -p /app/data && chmod 777 /app/data

# Hugging Face Spaces exposes port 7860 by default
EXPOSE 7860

# Run the FastAPI server
CMD ["uvicorn", "liebchen.api.server:app", "--host", "0.0.0.0", "--port", "7860"]
