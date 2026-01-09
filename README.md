# 🎬 Whisper Subtitles

<div align="center">

![Whisper Subtitles Logo](https://img.shields.io/badge/🎬-Whisper%20Subtitles-blue?style=for-the-badge)

**AI-powered subtitle generator using OpenAI Whisper**

[![License](https://img.shields.io/badge/License-Non--Commercial-red.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](docker-compose.yml)
[![OpenVINO](https://img.shields.io/badge/Intel-OpenVINO-0071C5.svg)](https://github.com/openvinotoolkit/openvino)

</div>

---


<div align="center">

## 🌐 Поддерживаемые языки интерфейса / Supported Interface Languages

Интерфейс приложения доступен на **15 языках** / The interface is available in **15 languages**:

| | | | |
|:---:|:---:|:---:|:---:|
| 🇷🇺 Русский | 🇬🇧 English | 🇺🇦 Українська | 🇰🇿 Қазақша |
| 🇩🇪 Deutsch | 🇫🇷 Français | 🇪🇸 Español | 🇮🇹 Italiano |
| 🇧🇷 Português | 🇯🇵 日本語 | 🇨🇳 中文 | 🇰🇷 한국어 |
| 🇹🇷 Türkçe | 🇸🇦 العربية | 🇮🇳 हिन्दी | |

📖 **Инструкция / Documentation:** [🇷🇺 Русский](#-русский) | [🇬🇧 English](#-english)

</div>

---

# 🇷🇺 Русский

## 📋 Описание

> 👂 **Создано для людей, которые заслуживают смотреть любое видео без барьеров**

**Whisper Subtitles** — это не просто программа, это **мост между миром звука и текста**.

🎬 Миллионы фильмов, сериалов и видео не имеют субтитров. Для людей с нарушениями слуха это означает невозможность наслаждаться контентом, который доступен всем остальным.

**Whisper Subtitles меняет это:**

- 🏠 **Домашние видео** — семейные записи станут доступны всем членам семьи
- 🎥 **Фильмы без субтитров** — наконец-то можно смотреть!
- 📚 **Видеолекции** — обучение без ограничений
- 🌍 **Документальные фильмы** — познавайте мир без барьеров
- 🎙️ **Подкасты и интервью** — вся информация теперь в тексте

Приложение использует передовую нейросеть **OpenAI Whisper**, оптимизированную для процессоров Intel через **OpenVINO**, что позволяет запустить его даже на недорогих мини-ПК.

### ✨ Возможности

- 🎯 **Автоматическое распознавание речи** — поддержка 99 языков
- 📁 **Множество источников** — загрузка видео, URL, магнет-ссылки, торренты
- � **Любые форматы видео** — MKV, MP4, AVI, MOV, WebM и другие
- 🎵 **Выбор аудиодорожки** — возможность выбрать нужную дорожку при обработке
- 📦 **Выборочная загрузка** — в торрентах можно выбрать только нужные серии/файлы
- ▶️ **Онлайн просмотр** — смотрите обработанные видео прямо в браузере
- 📝 **Экспорт субтитров** — скачивание в SRT формате
- 🎬 **Вшивание субтитров** — субтитры добавляются как отдельная дорожка в видеофайл
- 🎨 **Современный интерфейс** — адаптивный дизайн на 15 языках
- ⚡ **Оптимизация Intel** — ускорение через OpenVINO
- 🔒 **Безопасность** — авторизация с JWT токенами

### 🖥️ Системные требования

| Компонент | Минимум | Рекомендуется |
|-----------|---------|---------------|
| CPU | Intel N100 | Intel N150+ / Core i5+ |
| RAM | 4 GB | 8+ GB |
| Диск | 10 GB | 50+ GB (для моделей и видео) |
| ОС | Linux (Docker) | Ubuntu 22.04+ |

### 🚀 Быстрый старт

#### 1️⃣ Клонируйте репозиторий

```bash
git clone https://github.com/your-username/whisper-subtitles.git
cd whisper-subtitles
```

#### 2️⃣ Запустите Docker

```bash
docker compose up -d
```

Всё! Приложение запущено! 🎉

#### 3️⃣ Откройте в браузере

```
http://localhost:8000
```

**Данные для входа:**
- 👤 Логин: `admin`
- 🔑 Пароль: `admin123`

> ⚠️ **Важно!** Смените пароль в настройках после первого входа!

### 📊 Модели Whisper

| Модель | Размер | Скорость | Качество | Рекомендация |
|--------|--------|----------|----------|--------------|
| `tiny` | 75 MB | ~32x | ⭐ | Быстрые тесты |
| `base` | 142 MB | ~16x | ⭐⭐ | Черновики |
| `small` | 466 MB | ~10x | ⭐⭐⭐ | Баланс |
| `medium` | 1.5 GB | ~5x | ⭐⭐⭐⭐ | Хорошее качество |
| `large-v2` | 3 GB | ~3x | ⭐⭐⭐⭐⭐ | Максимальная точность |
| `large-v3-int4` | 1 GB | ~6x | ⭐⭐⭐⭐ | Самый быстрый V3 |
| `large-v3-int8` | 1.5 GB | ~4x | ⭐⭐⭐⭐⭐ | **Рекомендуется для Intel** |
| `large-v3-fp16` | 3 GB | ~3x | ⭐⭐⭐⭐⭐ | Максимальное качество V3 |

### 🔧 Расширенная настройка

#### Docker Compose с GPU Intel

```yaml
services:
  whisper:
    build: .
    container_name: whisper-subtitles
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./models:/app/models
    devices:
      - /dev/dri:/dev/dri  # Для Intel GPU
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - DEFAULT_MODEL=${DEFAULT_MODEL:-large-v3-int8}
      - CPU_THREADS=${CPU_THREADS:-4}
    restart: unless-stopped
```

#### Размещение за Nginx

```nginx
server {
    listen 80;
    server_name subtitles.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 10G;  # Для больших видео
    }
}
```

### 📁 Структура проекта

```
whisper-subtitles/
├── app/                    # Исходный код приложения
│   ├── static/            # Статические файлы (CSS, JS)
│   │   └── locales/       # Файлы локализаций
│   ├── tasks/             # Фоновые задачи
│   ├── main.py            # Точка входа FastAPI
│   └── database.py        # База данных SQLite
├── data/                   # Данные (создаётся автоматически)
│   ├── uploads/           # Загруженные файлы
│   ├── downloads/         # Скачанные файлы
│   ├── temp/              # Временные файлы
│   └── output/            # Готовые субтитры
├── models/                 # Модели Whisper (скачиваются автоматически)
├── docker-compose.yml      # Docker конфигурация
├── Dockerfile             # Сборка образа
├── requirements.txt       # Python зависимости
└── .env.example           # Пример переменных окружения
```

### ❓ Частые вопросы

<details>
<summary><b>Как изменить порт?</b></summary>

В `docker-compose.yml` измените:
```yaml
ports:
  - "8080:8000"  # Теперь доступно на порту 8080
```
</details>

<details>
<summary><b>Где хранятся субтитры?</b></summary>

В папке `./data/output/` в формате SRT.
</details>

<details>
<summary><b>Можно ли использовать без Docker?</b></summary>

Да, но потребуется вручную установить FFmpeg, aria2 и Python зависимости.
</details>

### 📄 Лицензия

Этот проект предназначен **только для некоммерческого использования**.

---

# 🇬🇧 English

## 📋 Description

> 👂 **Created for people who deserve to watch any video without barriers**

**Whisper Subtitles** is not just software, it's a **bridge between the world of sound and text**.

🎬 Millions of movies, TV shows, and videos don't have subtitles. For people with hearing impairments, this means being unable to enjoy content that's available to everyone else.

**Whisper Subtitles changes this:**

- 🏠 **Home videos** — family recordings become accessible to all family members
- 🎥 **Movies without subtitles** — finally, you can watch them!
- 📚 **Video lectures** — learning without limitations
- 🌍 **Documentaries** — explore the world without barriers
- 🎙️ **Podcasts and interviews** — all information now in text

The application uses the cutting-edge **OpenAI Whisper** neural network, optimized for Intel processors via **OpenVINO**, allowing it to run even on affordable mini-PCs.

### ✨ Features

- 🎯 **Automatic speech recognition** — 99 languages supported
- 📁 **Multiple input sources** — video files, URLs, magnet links, torrents
- 🎬 **Any video format** — MKV, MP4, AVI, MOV, WebM and more
- 🎵 **Audio track selection** — choose the desired audio track during processing
- 📦 **Selective download** — download only specific episodes/files from torrents
- ▶️ **Online playback** — watch processed videos directly in your browser
- 📝 **Subtitle export** — download in SRT format
- 🎬 **Subtitle embedding** — subtitles are added as a separate track in the video file
- 🎨 **Modern interface** — responsive design in 15 languages
- ⚡ **Intel optimization** — OpenVINO acceleration
- 🔒 **Security** — JWT token authorization

### 🖥️ System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | Intel N100 | Intel N150+ / Core i5+ |
| RAM | 4 GB | 8+ GB |
| Storage | 10 GB | 50+ GB (for models and videos) |
| OS | Linux (Docker) | Ubuntu 22.04+ |

### 🚀 Quick Start

#### 1️⃣ Clone the repository

```bash
git clone https://github.com/your-username/whisper-subtitles.git
cd whisper-subtitles
```

#### 2️⃣ Start Docker

```bash
docker compose up -d
```

That's it! The app is running! 🎉

#### 3️⃣ Open in browser

```
http://localhost:8000
```

**Login credentials:**
- 👤 Username: `admin`
- 🔑 Password: `admin123`

> ⚠️ **Important!** Change your password in settings after first login!

### 📊 Whisper Models

| Model | Size | Speed | Quality | Recommendation |
|-------|------|-------|---------|----------------|
| `tiny` | 75 MB | ~32x | ⭐ | Quick tests |
| `base` | 142 MB | ~16x | ⭐⭐ | Drafts |
| `small` | 466 MB | ~10x | ⭐⭐⭐ | Balance |
| `medium` | 1.5 GB | ~5x | ⭐⭐⭐⭐ | Good quality |
| `large-v2` | 3 GB | ~3x | ⭐⭐⭐⭐⭐ | Maximum accuracy |
| `large-v3-int4` | 1 GB | ~6x | ⭐⭐⭐⭐ | Fastest V3 |
| `large-v3-int8` | 1.5 GB | ~4x | ⭐⭐⭐⭐⭐ | **Recommended for Intel** |
| `large-v3-fp16` | 3 GB | ~3x | ⭐⭐⭐⭐⭐ | Maximum quality V3 |

### 🔧 Advanced Configuration

#### Docker Compose with Intel GPU

```yaml
services:
  whisper:
    build: .
    container_name: whisper-subtitles
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./models:/app/models
    devices:
      - /dev/dri:/dev/dri  # For Intel GPU
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - DEFAULT_MODEL=${DEFAULT_MODEL:-large-v3-int8}
      - CPU_THREADS=${CPU_THREADS:-4}
    restart: unless-stopped
```

#### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name subtitles.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 10G;  # For large videos
    }
}
```

### 📁 Project Structure

```
whisper-subtitles/
├── app/                    # Application source code
│   ├── static/            # Static files (CSS, JS)
│   │   └── locales/       # Localization files
│   ├── tasks/             # Background tasks
│   ├── main.py            # FastAPI entry point
│   └── database.py        # SQLite database
├── data/                   # Data (created automatically)
│   ├── uploads/           # Uploaded files
│   ├── downloads/         # Downloaded files
│   ├── temp/              # Temporary files
│   └── output/            # Ready subtitles
├── models/                 # Whisper models (downloaded automatically)
├── docker-compose.yml      # Docker configuration
├── Dockerfile             # Image build
├── requirements.txt       # Python dependencies
└── .env.example           # Environment variables example
```

### ❓ FAQ

<details>
<summary><b>How to change the port?</b></summary>

In `docker-compose.yml` change:
```yaml
ports:
  - "8080:8000"  # Now available on port 8080
```
</details>

<details>
<summary><b>Where are subtitles stored?</b></summary>

In `./data/output/` folder in SRT format.
</details>

<details>
<summary><b>Can I use without Docker?</b></summary>

Yes, but you'll need to manually install FFmpeg, aria2 and Python dependencies.
</details>

### 📄 License

This project is for **non-commercial use only**.

---

<div align="center">

**Made with ❤️ using open source software**

[⬆️ Back to top](#-whisper-subtitles)

</div>
