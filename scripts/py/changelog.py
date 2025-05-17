from pathlib import Path
import re
import logging

PROJECT_FOLDER = Path(__file__).resolve().parent.parent.parent
VERSION_FILE = PROJECT_FOLDER / "version.txt"
COMMIT_FILE = PROJECT_FOLDER / "commit.txt"
CHANGELOG_FILE = PROJECT_FOLDER / "CHANGELOG.md"

logging.basicConfig(level=logging.INFO)


def read_commit():
    try:
        with open(COMMIT_FILE, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        logging.error(f"Commit file {COMMIT_FILE} not found.")
        return None


def find_semantic_version(commit: str):
    pattern = r'\bv?(\d+\.\d+\.\d+(?:-\d+)?)\b'
    match = re.search(pattern, commit)
    if match:
        return f"v{match.group(1)}"

    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as file:
            version = file.read().strip()
            if not version.startswith("v"):
                version = "v" + version
            return version
    except FileNotFoundError:
        logging.error(f"Version file {VERSION_FILE} not found.")
        return "v0.0.0"


def update_changelog(commit: str):
    try:
        with open(CHANGELOG_FILE, "r", encoding="utf-8") as f:
            changelog = f.read()

        changelog_updated = changelog.replace("# CHANGELOG\n", f"# CHANGELOG\n\n#### {commit}\n")

        with open(CHANGELOG_FILE, "w", encoding="utf-8") as f:
            f.write(changelog_updated)
        logging.info("Changelog updated successfully.")
    except FileNotFoundError:
        logging.error(f"Changelog file {CHANGELOG_FILE} not found.")


def update_version_file(version: str):
    try:
        with open(VERSION_FILE, "w", encoding="utf-8") as file:
            file.write(version)
        logging.info("Version file updated successfully.")
    except FileNotFoundError:
        logging.error(f"Version file {VERSION_FILE} not found.")


def main():
    commit = read_commit()
    if not commit:
        logging.error("Commit could not be read; exiting.")
        return

    if commit.startswith("v"):
        version = find_semantic_version(commit)
        update_changelog(commit)
        update_version_file(version)


if __name__ == "__main__":
    main()
