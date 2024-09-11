"""
A script that counts an amount of lines of code in a project
"""


import os
from pathlib import Path

DIR = os.path.dirname(os.path.abspath(__file__))


def count_lines_in_python_files(directory, skip_files=None, skip_dirs=None, add_files=None):
    if skip_files is None:
        skip_files = []
    if skip_dirs is None:
        skip_dirs = []
    if add_files is None:
        skip_dirs = []

    total_lines = 0
    file_dict = {}

    for root, dirs, files in os.walk(directory):
        # Skip directories
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for file in files:
            if (file.endswith('.py') and file not in skip_files) or file in add_files:
                file_path = Path(root) / file
                with open(file_path, 'r', encoding='utf-8') as fl:
                    lines = fl.readlines()
                    total_lines += len(lines)
                    file_dict[str(file_path)] = len(lines)

    return str(total_lines)


skip_files_list = ['test.py']
add_files_list = ["README.md", "config.yaml", "requirements.txt"]
skip_dirs_list = ['venv', 'models',  "__pycache__", ".git", ".idea", "app_log", "sounds", "images", "grammar", "NED"]

with open(f"{os.path.dirname(DIR)}/README.md", "r+", encoding="utf-8") as f:
    readme = f.read()
    modified = readme.replace("lines of code:", f"lines of code: {count_lines_in_python_files(DIR, skip_files_list, skip_dirs_list, add_files_list)}")
    f.seek(0)
    f.write(modified)
