
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY campus_model.py .
COPY test_model.py .

CMD ["python", "-m", "pytest", "test_model.py", "-v"]
