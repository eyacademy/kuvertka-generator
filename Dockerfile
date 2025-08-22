# jackets/Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Системные пакеты: LibreOffice + шрифты
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice \
      fonts-dejavu-core fontconfig curl unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Ставим зависимости раньше, чтобы кэшировалось
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код и ресурсы
COPY . .

# Кастомные шрифты (если есть)
# COPY fonts /usr/local/share/fonts/custom
# RUN fc-cache -f -v

# Railway сам задаёт $PORT — НЕ хардкодим!
EXPOSE 0

# Если main.py в корне и FastAPI-приложение называется "app"
# иначе подставь свою точку входа
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "${PORT}"]
