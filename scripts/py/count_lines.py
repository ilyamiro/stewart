"""
A script that counts the number of lines of code in a project
"""

import os
import re
from pathlib import Path

PROJECT_FOLDER = Path(__file__).resolve().parent.parent.parent
README = PROJECT_FOLDER / "README.md"


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
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for file in files:
            if (file.endswith('.py') and file not in skip_files) or file in add_files:
                file_path = Path(root) / file
                with open(file_path, 'r', encoding='utf-8') as fl:
                    lines = fl.readlines()
                    total_lines += len(lines)
                    file_dict[str(file_path)] = len(lines)
    return str(total_lines)


skip_files_list = ['test.py', 'test2.py']
add_files_list = ["README.md", "requirements.txt", ]
skip_dirs_list = ['venv', 'models',  "__pycache__", ".git", ".idea", "app_log", "sounds", "images", "grammar", "animations"]

lines_of_code = count_lines_in_python_files(PROJECT_FOLDER, skip_files_list, skip_dirs_list, add_files_list)


def replace_lines(number):
    with open(README, "r", encoding="utf-8") as f:
        readme = f.read()

    pattern = r'Lines of code: \*\*\d+\*\*'
    new_content = re.sub(pattern, f'Lines of code: **{number}**', readme)

    with open(README, "w", encoding="utf-8") as f:
        f.write(new_content)


replace_lines(lines_of_code)

