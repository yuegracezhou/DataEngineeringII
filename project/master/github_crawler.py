import requests
import time
import json
import os
import random
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------- 环境变量 & 配置 ----------
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env'))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/117.0"
}

REPO_SEARCH_URL = "https://api.github.com/search/repositories"
CODE_SEARCH_URL = "https://api.github.com/search/code"
TOTAL_REPOS = 1000
PER_PAGE = 100
JSON_FILENAME = "projects.json"

DATE_RANGES = [
    "created:<2018-01-01",
    "created:2018-01-01..2020-01-01",
    "created:2020-01-01..2022-01-01",
    "created:>2022-01-01"
]

SENSITIVE_ORGS = ["alibaba", "netflix", "spring-projects", "apache", "baidu", "google"]
ENABLE_SKIP_SENSITIVE = True  # ← 是否跳过敏感组织 repo

# ---------- 带重试机制的 session ----------
session = requests.Session()
retries = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

checked_maven_cache = {}

def is_sensitive_repo(full_name):
    full_name_lower = full_name.lower()
    return any(org in full_name_lower for org in SENSITIVE_ORGS)

def check_if_maven(full_name):
    if full_name in checked_maven_cache:
        return checked_maven_cache[full_name]

    params = {"q": f"filename:pom.xml repo:{full_name}"}
    try:
        response = session.get(CODE_SEARCH_URL, headers=HEADERS, params=params, timeout=10)

        # 打印剩余请求额度
        remaining = response.headers.get("X-RateLimit-Remaining", "?")
        print(f"[DEBUG] Remaining quota: {remaining} for repo {full_name}")

        if response.status_code == 200:
            result = len(response.json().get("items", [])) > 0
        else:
            print(f"[WARN] check_if_maven: status {response.status_code} for {full_name}")
            result = False

        checked_maven_cache[full_name] = result
        return result

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Exception in check_if_maven for {full_name}: {e}")
        checked_maven_cache[full_name] = False
        return False

def crawl_java_maven_projects():
    all_projects = []
    seen_ids = set()

    for date_range in DATE_RANGES:
        page = 1
        while len(all_projects) < TOTAL_REPOS:
            if page > 10:
                print(f"[INFO] Reached page limit for query: {date_range}")
                break

            print(f"[INFO] Searching repos: {date_range}, page {page}")
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
                    print(f"[ERROR] Repo search failed: {response.status_code}")
                    print(response.text)
                    break

                items = response.json().get("items", [])
                if not items:
                    print(f"[INFO] No more items in {date_range}, page {page}")
                    break

                for repo in items:
                    repo_id = repo["id"]
                    full_name = repo["full_name"]

                    if repo_id in seen_ids:
                        continue
                    seen_ids.add(repo_id)

                    # 🧱 可选跳过敏感组织仓库
                    if ENABLE_SKIP_SENSITIVE and is_sensitive_repo(full_name):
                        print(f"[SKIP] Sensitive repo skipped: {full_name}")
                        continue

                    # ✅ 判断是否含 pom.xml
                    if not check_if_maven(full_name):
                        time.sleep(2.5 + random.uniform(0.5, 1.0))
                        continue

                    time.sleep(2.5 + random.uniform(0.5, 1.0))

                    project_data = {
                        "name": repo["name"],
                        "full_name": full_name,
                        "html_url": repo["html_url"],
                        "clone_url": repo["clone_url"],
                        "stargazers_count": repo["stargazers_count"],
                        "forks_count": repo["forks_count"],
                        "language": repo["language"]
                    }

                    all_projects.append(project_data)
                    print(f"[OK] Added: {full_name} ({len(all_projects)}/{TOTAL_REPOS})")

                    if len(all_projects) >= TOTAL_REPOS:
                        break

                page += 1
                time.sleep(1.5)

            except requests.exceptions.RequestException as e:
                print(f"[ERROR] Exception during repo search: {e}")
                break

        if len(all_projects) >= TOTAL_REPOS:
            break

    print(f"\n[INFO] Saving {len(all_projects)} projects to {JSON_FILENAME}...")
    with open(JSON_FILENAME, "w", encoding="utf-8") as f:
        json.dump(all_projects, f, indent=4, ensure_ascii=False)
    print("[DONE] JSON file saved successfully.")

# ---------- 启动 ----------
if __name__ == "__main__":
    crawl_java_maven_projects()
