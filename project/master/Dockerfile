FROM python:3.11-slim
WORKDIR /app

#Installing python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

#Copy the crawler code
COPY github_crawler.py clone_url.py ./

CMD ["python", "github_crawler.py"]

