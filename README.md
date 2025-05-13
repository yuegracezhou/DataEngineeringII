# 🧪 DataEngineeringII Project – Group 17

## ⚙️ Demonstration of Horizontal Scaling with Lightweight Virtualization for Large-Scale Unit Test Analysis of Open-Source Projects

### 🔑 Key Words  
**Distributed Computing Infrastructures**, **Scalability**, **Orchestration**, **Software Deployment**

---

## 📘 Project Overview

Analyzing large-scale open-source projects is an active research area that helps researchers understand real-world development issues. However, dealing with the large corpus of code is time-consuming, especially when the analysis is done at runtime.

To address this, our project aims to:

- Develop a scalable framework for analyzing open-source Java projects.
- Optimize unit test execution using lightweight virtualization and container orchestration.
- Focus on **automation**, **contextualization**, and **orchestration** of project execution.

We target **1000 Java projects** that:

- Use the **Maven** build system (`pom.xml`)
- Contain **unit tests** (`src/test/java`)

---

## 🧱 Architecture Goals

- ✅ Design a **scalable architecture** to enable horizontal scaling.
- ✅ Implement **automation** for task deployment and execution.
- ✅ Enable **contextualization** for efficient VM/container configuration.
- ✅ Integrate **orchestration** to manage distributed workloads.

Recommended scalability tests:

- 🔹 Strong scalability  
- 🔹 Weak scalability

---

## 🔍 Part 1 – GitHub Java Project Crawler

This repository contains a Python-based crawler that uses the GitHub REST API to find and filter Java repositories.

### 📦 Features

- Queries GitHub using the [GitHub REST API](https://docs.github.com/en/rest)
- Filters projects using Maven and checks for unit tests
- Outputs the result in JSON format
- Designed as the first step of a distributed framework

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/yuegracezhou/DataEngineeringII.git
cd DataEngineeringII

### 2. Create and Activate Virtual Environment

python3 -m venv github_env
source github_env/bin/activate

### 3. Install Dependencies

pip install -r requirements.txt

### 4. Run the Crawler

python crawler.py

### Output

filtered_projects.json

---

📌 **Requires Python 3.10 or above**  
✅ **Tested on Python 3.10.12**

---
