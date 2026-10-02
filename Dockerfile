FROM python:3.12-slim

WORKDIR /app

# Install git inside the container so you can use it there
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
    
RUN pip install --no-cache-dir mcp pytest
COPY . .

CMD ["python", "-c", "print('container is running')"]