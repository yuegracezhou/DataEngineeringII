FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY github_realtime_crawler.py .

CMD ["python", "github_crawler_paged.py"]

