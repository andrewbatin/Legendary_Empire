# Использовать официальный образ Python
FROM python:3.11-slim

# Установить рабочую директорию
WORKDIR /app

# Установить системные зависимости
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Скопировать файл требований
COPY requirements.txt .

# Установить Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Скопировать код приложения
COPY . .

# Создать директорию для логов
RUN mkdir -p logs

# Установить переменные окружения
ENV PYTHONUNBUFFERED=1

# Запустить бота
CMD ["python", "bot.py"]