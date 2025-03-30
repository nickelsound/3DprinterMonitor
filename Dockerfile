# Použij Python 3.12 jako základní image
FROM python:3.12-slim

# Nastav pracovní adresář v kontejneru
WORKDIR /app

# Zkopíruj requirements.txt do kontejneru
COPY requirements.txt .
COPY .env .

# Nainstaluj závislosti
RUN pip install --no-cache-dir -r requirements.txt

# Zkopíruj zbytek aplikace do kontejneru
COPY printer_monitor.py .

# Spusť Python skript
CMD ["python", "./printer_monitor.py"]