# LLM Telegram Video Bot

Бот для обработки видео с помощью искусственного интеллекта в Telegram.

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Создание виртуального окружения
python -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Скопируйте шаблон и заполните реальные значения:

```bash
cp env.template .env
# Отредактируйте .env файл с вашими токенами
```

### 3. Запуск бота

#### Обычный запуск (файлы до 50MB)

```bash
# Локальный запуск
python src/main.py
```

#### Запуск с поддержкой больших файлов (до 2GB)

Для загрузки видео больше 50MB используйте локальный Telegram Bot API сервер:

##### Получите API ключи

1. Перейдите на https://my.telegram.org/auth
2. Получите `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`

##### Настройте переменные окружения

В файле `.env` добавьте:

```env
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here
```

##### Запуск через Docker (рекомендуется)

```bash
docker-compose up --build -d
docker-compose logs -f neurodlb-bot
```

##### Или запуск вручную

```bash
# Запустите локальный Bot API сервер
docker run -d --name telegram-bot-api \
  -p 8081:8081 \
  -e TELEGRAM_API_ID=your_api_id \
  -e TELEGRAM_API_HASH=your_api_hash \
  aiogram/telegram-bot-api:latest

# Установите переменную окружения
export TELEGRAM_BOT_API_URL=http://localhost:8081

# Запустите бота
python src/main.py
```

**✅ Результат:** После настройки сможете загружать видео до **2GB**!

## 📁 Структура проекта

```
src/
├── bot.py              # Основной файл бота
├── video_processor.py  # Обработка видео
├── llm_handler.py      # Работа с Mistral API
├── utils.py           # Вспомогательные функции
└── config.py          # Конфигурация
```

## 🛠 Технологии

- **Python 3.11+**
- **python-telegram-bot** - Telegram Bot API
- **yt-dlp** - Скачивание видео
- **ffmpeg-python** - Обработка видео
- **mistralai** - ИИ для обработки текста

## 📋 Текущий статус

✅ Итерация 1: Базовая настройка проекта завершена
⏳ Итерация 2: В процессе - разработка простого Telegram бота

## 📖 Документация

- [Техническое видение](doc/vision.md)
- [План разработки](doc/tasklist.md)
- [Правила разработки](conventions.md)

## 🤝 Contributing

Проект находится в активной разработке. Следуйте правилам из `conventions.md`.
