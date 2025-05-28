# GitHub Crawler Module README

## Project Goal

This module is designed to automatically crawl large-scale Java (Maven-based) open-source projects from GitHub. The collected metadata is used for automated unit testing and analysis. The crawler supports two operating modes:

- Save project information as a local JSON file
- Stream project information to a RabbitMQ queue for parallel processing by distributed workers

## Architecture Overview

```
+-------------------------+
|     GitHub Crawler     |
|-------------------------|
|  - GitHub API queries   |
|  - pom.xml detection    |
|  - Sensitive repo filter|
|  - Date range paging    |
|  - Save or stream data  |
+-------------------------+
              ↓
  [1] Save to local JSON file (offline mode)
              OR
  [2] Stream to RabbitMQ (real-time mode)
```

## Technologies Used

| Technology     | Purpose                               |
| -------------- | ------------------------------------- |
| Python         | Main scripting language               |
| GitHub API     | Project search & pom.xml detection    |
| Docker         | Containerized deployment              |
| Docker Compose | Launching multiple crawler containers |
| RabbitMQ       | Optional message queue                |
| dotenv         | Environment variable management       |

## Two Run Modes

### Mode 1: Save to Local JSON File

Used for debugging or quota-limited scenarios. Each crawler writes to `output_crawlerX.json`.

```env
SAVE_TO_FILE=True
SEND_TO_RABBITMQ=False
```

### Mode 2: Stream to RabbitMQ

Each project is streamed directly to the message queue for worker-side parallel processing.

```env
SAVE_TO_FILE=False
SEND_TO_RABBITMQ=True
```

## Parallel Crawler Strategy

To speed up crawling and avoid duplication, multiple crawler instances are deployed using:

- Different `DATE_RANGES` (e.g., created year windows)
- Different pagination offsets (`START_PAGE`, `PAGE_STEP`)
- Separate GitHub tokens for API quota separation

**Example configuration:**

```
crawler1: DATE_RANGES=A+B, START_PAGE=1
crawler2: DATE_RANGES=C+D, START_PAGE=2
```

## Directory Structure

```
crawler/crawler_stream/
├── github_crawler.py            # Original crawler (push-enabled)
├── github_crawler_paged.py      # Paged version for parallel crawling
├── Dockerfile                   # Container build file
├── requirements.txt             # Python dependencies
├── .env.crawler1 / .env.crawler2 # Env files for each instance
├── docker-compose.yml           # Launches both containers
└── output_crawler1.json         # Output sample
```

## How to Run

### Build and Run Both Crawlers in Parallel

```bash
docker-compose up --build
```

```

##  Team Contribution

Authors: **Tingting Lyu & Zhou Yue**
The crawler module was jointly designed and implemented with **equal contribution** by both members.
```
