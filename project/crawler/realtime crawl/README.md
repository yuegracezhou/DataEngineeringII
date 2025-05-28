# 🐇 Realtime GitHub Crawler with RabbitMQ

This module contains a **realtime GitHub crawler** that continuously fetches open-source Java + Maven projects from GitHub and **streams them directly to a RabbitMQ queue** for distributed processing.

---

## 📌 Folder Purpose

This folder is **isolated** from the file-based crawler used in previous phases, and is designed specifically for **stream-based data collection**, supporting concurrent crawling and horizontal scaling.

---

## 🚀 Features

- 🔁 Streams project metadata **directly into RabbitMQ** (no local storage)
- ⏱️ Supports **parallel crawling** via multiple containers
- ✅ Avoids duplicate results using:
  - Date range sharding (`DATE_RANGES`)
  - Page offset partitioning (`START_PAGE` + `PAGE_STEP`)
- 🐳 Ready to deploy with Docker Compose
- 💬 Fully configurable via `.env` files

---

## 📁 Files

| File                          | Purpose                                 |
|-------------------------------|------------------------------------------|
| `github_realtime_crawler.py` | Main Python crawler script (stream mode) |
| `Dockerfile`                 | Docker build config                      |
| `requirements.txt`           | Python dependencies                      |
| `docker-compose.yml`         | Launches multiple crawler containers     |

---

## ⚙️ Environment Variables (.env)

Each container uses its own `.env` file, example:

```env
GITHUB_TOKEN=your_github_token_here
DATE_RANGES=created:2017-01-01..2018-01-01
START_PAGE=1
PAGE_STEP=2
TOTAL_REPOS=500
RABBITMQ_HOST=broker
RABBITMQ_QUEUE=project_queue_stream



How to Run
Place two .env files (e.g. .env.crawler1, .env.crawler2) in this folder.

Launch the crawler containers:

docker-compose up --build
