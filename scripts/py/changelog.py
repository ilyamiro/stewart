from pathlib import Path

PROJECT_FOLDER = Path(__file__).resolve().parent.parent.parent


with open(f"{PROJECT_FOLDER}/commit.txt", "r", encoding="utf-8") as file:
    commit_msg = file.read()


with open(f"{PROJECT_FOLDER}/CHANGELOG.md", "r", encoding="utf-8") as f:
    changelog = f.read()

changelog_2 = changelog.replace("# CHANGELOG\n", f"# CHANGELOG\n\n### {commit_msg}")


with open(f"{PROJECT_FOLDER}/CHANGELOG.md", "w", encoding="utf-8") as f:
    f.write(changelog_2)

