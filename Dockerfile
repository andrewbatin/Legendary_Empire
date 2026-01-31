FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY . .

# Render порт (ОБЯЗАТЕЛЬНО 10000)
EXPOSE 10000

# Создание папки для логов
RUN mkdir -p /app/logs

ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
