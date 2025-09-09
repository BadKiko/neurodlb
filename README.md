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

```bash
# Локальный запуск
python src/main.py

# Или через Docker
docker-compose up --build
```

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
