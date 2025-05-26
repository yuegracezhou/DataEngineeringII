# github_crawler_paged.py
import requests, time, json, os, random
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
START_PAGE = int(os.getenv("START_PAGE", 1))     # 爬虫起始页
PAGE_STEP = int(os.getenv("PAGE_STEP", 1))       # 每次跳多少页（默认1页）
TOTAL_REPOS = int(os.getenv("TOTAL_REPOS", 500)) # 每个容器爬多少条
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "output.json")  # 输出文件名

# 多个时间段用逗号分隔
RAW_DATE_RANGES = os.getenv("DATE_RANGES", "created:>2015-01-01")
DATE_RANGES = [r.strip() for r in RAW_DATE_RANGES.split(",") if r.strip()]

PER_PAGE = 100

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Mozilla/5.0"
}

REPO_SEARCH_URL = "https://api.github.com/search/repositories"
CODE_SEARCH_URL = "https://api.github.com/search/code"

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

# ❌ 暂时注释掉消息队列发送
# def send_to_rabbitmq(project_data): ...

def crawl():
    seen_ids = set()
    total_collected = 0
    all_projects = []

    for date_range in DATE_RANGES:
        page = START_PAGE
        while total_collected < TOTAL_REPOS:
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

                    # ❌ 不推送 RabbitMQ，改为保存
                    all_projects.append(project_data)
                    total_collected += 1
                    print(f"[OK] Added: {repo['full_name']} ({total_collected}/{TOTAL_REPOS})")

                    if total_collected >= TOTAL_REPOS:
                        break
                page += PAGE_STEP
                time.sleep(1.5)
            except Exception as e:
                print(f"[ERROR] Request error: {e}")
                break

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_projects, f, indent=4, ensure_ascii=False)
    print(f"[DONE] Saved {total_collected} projects to {OUTPUT_FILE}")

if __name__ == "__main__":
    crawl()

