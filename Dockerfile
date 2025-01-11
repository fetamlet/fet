# Используем базовый образ Python
FROM python:3.9-slim

# Создаем папку для бота
WORKDIR /app

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install -r requirements.txt

# Копируем код бота
COPY . .

# Запускаем бота
CMD ["python", "bot.py"]