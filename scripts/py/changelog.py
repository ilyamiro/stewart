from pathlib import Path
import re
import subprocess

PROJECT_FOLDER = Path(__file__).resolve().parent.parent.parent
VERSION_FILE = PROJECT_FOLDER / "version.txt"


def find_semantic_version(commit: str):
    pattern = r'(\d+\.\d+\.\d+)'
    match = re.search(pattern, commit)
    if match:
        return match.group()
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as file:
            return "v" + file.read().strip()
    except FileNotFoundError:
        logging.error(f"Version file {VERSION_FILE} not found.")
        return "v0.0.0"


def update_changelog(commit: str):
    with open(f"{PROJECT_FOLDER}/CHANGELOG.md", "r", encoding="utf-8") as f:
        changelog = f.read()

    changelog_updated = changelog.replace("# CHANGELOG\n", f"# CHANGELOG\n\n### {commit}")

    with open(f"{PROJECT_FOLDER}/CHANGELOG.md", "w", encoding="utf-8") as f:
        f.write(changelog_updated)


def update_version_txt(commit: str):
    version = find_semantic_version(commit)

    with open(VERSION_FILE, "w", encoding="utf-8") as file:
        file.write(version)


def main():
    commit = subprocess.run(['git', 'log', "-1", "--pretty=%B"], capture_output=True, text=True).stdout

    if commit.startswith("v"):
        update_changelog(commit)
        update_version_txt(commit)


main()

