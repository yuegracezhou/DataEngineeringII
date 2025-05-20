import os
import json
import subprocess
import shutil

# -------------------------
# Define paths and directories
# -------------------------
PROJECTS_FILE = "projects.json"
DOWNLOAD_DIR = "downloaded_projects"
TEST_CODE_DIR = "test_codes"

# -------------------------
# Clone repositories and collect test code
# -------------------------
def clone_repo(clone_url, project_name):
    project_dir = os.path.join(DOWNLOAD_DIR, project_name)
    if not os.path.exists(project_dir):
        print(f"[INFO] Cloning {project_name}...")
        subprocess.run(["git", "clone", clone_url, project_dir])

def collect_test_code(project_name):
    project_dir = os.path.join(DOWNLOAD_DIR, project_name)
    test_code_dir = os.path.join(project_dir, "src/test/java")
    
    if os.path.exists(test_code_dir):
        # Create a target directory for this project in the test_codes directory
        target_dir = os.path.join(TEST_CODE_DIR, project_name)
        os.makedirs(target_dir, exist_ok=True)
        
        for root, dirs, files in os.walk(test_code_dir):
            for file in files:
                if file.endswith(".java"):
                    # Copy each Java test file to the target directory
                    shutil.copy(os.path.join(root, file), os.path.join(target_dir, file))
        print(f"[INFO] Collected test code for {project_name}")
    else:
        print(f"[INFO] No test code found for {project_name}")

def process_projects():
    with open(PROJECTS_FILE, "r") as file:
        projects = json.load(file)
    
    # Loop through each project and clone repo, then collect test code
    for project in projects:
        clone_url = project["clone_url"]
        project_name = project["name"]
        
        # Clone the repo and collect test code
        clone_repo(clone_url, project_name)
        collect_test_code(project_name)

if __name__ == "__main__":
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
    if not os.path.exists(TEST_CODE_DIR):
        os.makedirs(TEST_CODE_DIR)
    
    process_projects()

