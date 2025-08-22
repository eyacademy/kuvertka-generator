FROM python:3.10-slim

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    libreoffice \
    fonts-dejavu \
    curl unzip fontconfig \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Копируем кастомные шрифты (если есть)
COPY fonts /usr/share/fonts/truetype/custom
RUN fc-cache -f -v

# Обновляем pip и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем приложение
COPY . .

EXPOSE 10000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]