
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY publisher/publisher.py .
COPY articles.json .

CMD ["python", "publisher.py"]
