FROM python:3.10-slim

# Install exiftool
RUN apt-get update && \
    apt-get install -y exiftool && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["python", "app/main.py"]
