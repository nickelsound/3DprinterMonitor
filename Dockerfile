FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
COPY .env .

RUN pip install --no-cache-dir -r requirements.txt

COPY printer_monitor.py .

CMD ["python", "./printer_monitor.py"]
