FROM python:3.11-slim

# Установка системных библиотек SQLite для правильной работы базы данных
RUN apt-get update && apt-get install -y sqlite3 libsqlite3-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "feedback_bot.py"]
