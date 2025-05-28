FROM python:3.11-slim

WORKDIR /app

#Install python and git and dependencies
RUN apt-get update \
&& apt-get install -y --no-install-recommends \
    default-jdk \
    maven \
    git \
&& rm -rf /var/lib/apt/lists/*

#Install python dependencies
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

#Copy the worker(consumer) script
COPY worker.py ./

CMD ["python", "worker.py"]
