# github_crawler_paged.py
import requests, time, json, os, random, pika
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "project_queue")
START_PAGE = int(os.getenv("START_PAGE", 1))  # 分别从 page=1 和 page=2 开始
PAGE_STEP = int(os.getenv("PAGE_STEP", 2))    # 每次 +2

TOTAL_REPOS = int(os.getenv("TOTAL_REPOS", 500))  # 每个 crawler 采集数量
PER_PAGE = 100

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Mozilla/5.0"
}

REPO_SEARCH_URL = "https://api.github.com/search/repositories"
CODE_SEARCH_URL = "https://api.github.com/search/code"

DATE_RANGES = [
    "created:<2018-01-01",
    "created:2018-01-01..2020-01-01",
    "created:2020-01-01..2022-01-01",
    "created:>2022-01-01"
]

SENSITIVE_ORGS = ["alibaba", "netflix", "spring-projects", "apache", "baidu", "google"]
ENABLE_SKIP_SENSITIVE = True
checked_maven_cache = {}

session = requests.Session()
retries = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)

def is_sensitive_repo(full_name):
    return any(org in full_name.lower() for org in SENSITIVE_ORGS)

def check_if_maven(full_name):
    if full_name in checked_maven_cache:
        return checked_maven_cache[full_name]
    params = {"q": f"filename:pom.xml repo:{full_name}"}
    try:
        response = session.get(CODE_SEARCH_URL, headers=HEADERS, params=params, timeout=10)
        result = response.status_code == 200 and len(response.json().get("items", [])) > 0
        checked_maven_cache[full_name] = result
        return result
    except:
        checked_maven_cache[full_name] = False
        return False

def send_to_rabbitmq(project_data):
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=RABBITMQ_QUEUE,
            body=json.dumps(project_data),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        print(f"[SENT] {project_data['full_name']}")
        connection.close()
    except Exception as e:
        print(f"[ERROR] Failed to send {project_data['full_name']}: {e}")

def crawl():
    seen_ids = set()
    total_sent = 0

    for date_range in DATE_RANGES:
        page = START_PAGE
        while total_sent < TOTAL_REPOS:
            print(f"[INFO] Searching: {date_range}, page {page}")
            params = {
                "q": f"language:Java pom.xml in:readme {date_range}",
                "per_page": PER_PAGE,
                "page": page,
                "sort": "stars",
                "order": "desc"
            }
            try:
                response = session.get(REPO_SEARCH_URL, headers=HEADERS, params=params, timeout=10)
                if response.status_code != 200:
                    break
                items = response.json().get("items", [])
                if not items:
                    break

                for repo in items:
                    if repo["id"] in seen_ids:
                        continue
                    seen_ids.add(repo["id"])
                    if ENABLE_SKIP_SENSITIVE and is_sensitive_repo(repo["full_name"]):
                        continue
                    if not check_if_maven(repo["full_name"]):
                        continue

                    project_data = {
                        "name": repo["name"],
                        "full_name": repo["full_name"],
                        "html_url": repo["html_url"],
                        "clone_url": repo["clone_url"],
                        "stargazers_count": repo["stargazers_count"],
                        "forks_count": repo["forks_count"],
                        "language": repo["language"]
                    }

                    send_to_rabbitmq(project_data)
                    total_sent += 1
                    if total_sent >= TOTAL_REPOS:
                        break
                page += PAGE_STEP
                time.sleep(1.5)
            except Exception as e:
                print(f"[ERROR] Request error: {e}")
                break

    print(f"[INFO] Crawler done. Sent {total_sent} projects.")

if __name__ == "__main__":
    crawl()

