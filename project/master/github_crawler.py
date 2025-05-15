# github_crawler.py

import requests
import time
import json
import os
from dotenv import load_dotenv

# 加载项目根目录下的 .env 文件
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env'))

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}
SEARCH_URL = "https://api.github.com/search/code"
REPO_URL_TEMPLATE = "https://api.github.com/repos/{full_name}"
QUERY = "filename:pom.xml"
PER_PAGE = 100
TOTAL_REPOS = 1000
JSON_FILENAME = "projects.json"

def get_full_repo_info(full_name):
    """获取仓库的完整信息，包括语言"""
    url = REPO_URL_TEMPLATE.format(full_name=full_name)
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"[WARN] Failed to fetch repo: {full_name} - Status {response.status_code}")
        return None

def crawl_maven_java_projects():
    all_projects = []
    seen_repo_ids = set()
    page = 1

    while len(all_projects) < TOTAL_REPOS:
        print(f"[INFO] Fetching code search page {page}...")
        params = {
            "q": QUERY,
            "per_page": PER_PAGE,
            "page": page
        }

        response = requests.get(SEARCH_URL, headers=HEADERS, params=params)

        if response.status_code != 200:
            print(f"[ERROR] GitHub API Error: {response.status_code}")
            print(response.text)
            break

        data = response.json()
        items = data.get("items", [])

        if not items:
            print("[INFO] No more items found.")
            break

        for item in items:
            repo = item["repository"]
            repo_id = repo["id"]
            full_name = repo["full_name"]

            if repo_id in seen_repo_ids:
                continue
            seen_repo_ids.add(repo_id)

            # 获取完整仓库信息
            full_repo = get_full_repo_info(full_name)
            if not full_repo:
                continue

            if full_repo.get("language") != "Java":
                continue

            project_data = {
                "name": full_repo["name"],
                "full_name": full_repo["full_name"],
                "html_url": full_repo["html_url"],
                "clone_url": full_repo["clone_url"],
                "stargazers_count": full_repo["stargazers_count"],
                "forks_count": full_repo["forks_count"],
                "language": full_repo["language"]
            }
            all_projects.append(project_data)
            print(f"[OK] Added: {full_name} ({len(all_projects)}/{TOTAL_REPOS})")

            if len(all_projects) >= TOTAL_REPOS:
                break

            time.sleep(1)  # 防止触发速率限制

        page += 1
        time.sleep(2)

    print(f"[INFO] Saving {len(all_projects)} projects to {JSON_FILENAME}...")
    with open(JSON_FILENAME, mode="w", encoding="utf-8") as file:
        json.dump(all_projects, file, indent=4, ensure_ascii=False)

    print("[DONE] JSON file saved successfully.")

if __name__ == "__main__":
    crawl_maven_java_projects()
