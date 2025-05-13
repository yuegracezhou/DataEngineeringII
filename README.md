# DataEngineeringII Proejct - Group 17
## Demonstration of horizontal scaling with lightweight virtualization approach for large-scale unit test analysis of open-source projects
### ⭐️ Key Words: Distributed Computing Infrastructures, Scalability, Orchestration, Software Deployment

## Part 1 - GitHub Java Project Crawler

This repository contains a Python-based web crawler for identifying open-source Java projects on GitHub that:

- Use the **Maven** build system (`pom.xml`)
- Include **unit tests** (i.e. have a `src/test/java` folder)

📌 Requires **Python 3.10 or above**  
Tested on **Python 3.10.12**

## 🧰 Features

- Uses GitHub REST API
- Filters repositories based on build system and presence of test code
- Saves results in JSON format
- Designed to support horizontal scaling and contextualization

## 🐍 Getting Started

1. **Clone this repository:**

```bash
git clone https://github.com/yuegracezhou/DataEngineeringII.git
cd DataEngineeringII.git

2. **Create and activate a virtual environment::**

python3 -m venv github_env
source github_env/bin/activate

3. **Install dependencies:**

pip install -r requirements.txt

4. **Run the crawler:**

python crawler.py

5. **Output**

Filtered project list saved to: filtered_projects.json

