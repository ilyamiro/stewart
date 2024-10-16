from pathlib import Path
import subprocess

PROJECT_FOLDER = Path(__file__).resolve().parent.parent.parent

COMMIT_MSG = subprocess.run(['git', 'log', "-1", "--pretty=%B"], capture_output=True, text=True).stdout

if COMMIT_MSG.startswith("v"):
    with open(f"{PROJECT_FOLDER}/CHANGELOG.md", "r", encoding="utf-8") as f:
        changelog = f.read()

    changelog_updated = changelog.replace("# CHANGELOG\n", f"# CHANGELOG\n\n### {COMMIT_MSG}")

    with open(f"{PROJECT_FOLDER}/CHANGELOG.md", "w", encoding="utf-8") as f:
        f.write(changelog_2)




