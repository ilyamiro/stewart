import os
from pathlib import Path
import subprocess
import re
import logging
from datetime import date
from pyrogram import Client
import shutil
import pyrogram.errors


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

logging.basicConfig(level=logging.INFO)

CHANNEL = "@stewart_github"
REPO_URL = "https://github.com/ilyamiro/stewart"

with open(f"{PROJECT_DIR}/version.txt", "r", encoding="utf-8") as file:
    version = file.read()


def run_git_command(args, use_shell=False):
    try:
        result = subprocess.run(args, capture_output=True, text=True, shell=use_shell, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running command {args}: {e}")
        return None


def replace_repeated_chars(input_string, char):
    pattern = f"{re.escape(char)}+"
    return re.sub(pattern, char, input_string)


def format_commit_changes(raw_changes):
    change_lines = raw_changes.strip().split("\n")
    formatted_changes = "\n".join([f"• {line.strip()}" for line in change_lines if line.strip()])

    formatted_changes = replace_repeated_chars(formatted_changes, "+")
    formatted_changes = replace_repeated_chars(formatted_changes, "-")
    formatted_changes = replace_repeated_chars(formatted_changes, " ")
    return formatted_changes


def build_telegram_message(commit_info, changes, short=False):
    return f"""**Новый коммит** 
Версия: **{version}**
    
Репозиторий: **{commit_info["repository"]}**
Ветка: **{commit_info['branch']}**

Автор: **{commit_info['author']}**
Дата: **{commit_info['date']}**

{commit_info['message'][1]}

{changes if not short else "Измененные файлы скрыты из-за превышения длины сообщения"}

**[Cсылка на коммит]({REPO_URL}/commit/{commit_info['hash']})**

__автоматически сгенерированное сообщение__
"""


def build_edit_message():
    return f"""Всем привет!

Меня зовут Илья, я 17 летний разработчик

В этом телеграм канале я буду показывать свой прогресс в создании помощника по имени Стюарт. Я буду постить мой прогресс, дневные задачи и прогресс на русском и английском языках

Текущая версия ассистента: **{version}**
 
Сайт проекта и документация: https://ilyamiro.github.io/stewart/

GitHub: https://github.com/ilyamiro/Stewart/tree/development
YouTube: https://youtube.com/@stewart.github

Мой телеграм: http://t.me/sacrificeit
"""


def load_rus():
    try:
        with open(f"{PROJECT_DIR}/commit_ru.txt", "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        return None


def get_commit_info():
    rus_commit = load_rus()
    commit_info = {
        'message': [run_git_command(['git', 'log', '-1', '--pretty=%B']), rus_commit],
        'hash': run_git_command(['git', 'log', '-1', '--pretty=%H']),
        'date': run_git_command(['git', 'log', '-1', '--pretty=%ad', '--date=iso']),
        'author': run_git_command(['git', 'log', '-1', '--pretty=%an']),
        'branch': run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        'repository': run_git_command(["basename -s .git `git remote get-url origin`"], use_shell=True)
    }
    return commit_info


def get_commit_changes(commit_hash):
    raw_changes = run_git_command(['git', 'show', '--stat', '--pretty=', commit_hash])
    if raw_changes:
        return format_commit_changes(raw_changes)
    return ""


def construct_to_blog(commit_info, changes):
    return f"""---
slug: commit-{version.replace('.', '-')}
title: Commit - {version}
authors: [ilyamiro]
tags: [commit]    
---

**New commit** 
Version: **{version}**
    
Repository: **{commit_info["repository"]}**
Branch: **{commit_info['branch']}**

Date: **{commit_info['date']}**

<!-- truncate -->

{commit_info['message'][0]}

**[Link to a commit]({REPO_URL}/commit/{commit_info['hash']})**

Follow **Stewart** on telegram: https://t.me/stewart_github
"""


def main():
    commit_info = get_commit_info()
    if not commit_info['message'][0].startswith("v"):
        logging.info("No new version commit detected, exiting.")
        return

    changes = get_commit_changes(commit_info['hash'])

    telegram_message = build_telegram_message(commit_info, changes)
    blog_message = construct_to_blog(commit_info, changes)

    today_str = date.today().strftime("%Y-%m-%d")
    filename = f"{today_str}-commit-{version.replace('.', '-')}.md"
    wiki_dir = "/home/ilyamiro/Life/projects/stewart.wiki/"

    file_path = os.path.join(f"{wiki_dir}/blog", filename)
    with open(file_path, "w") as f:
        f.write(blog_message)

    subprocess.run(["npm", "run", "build"], cwd=wiki_dir, check=True)

    # Step 4: Remove existing docs directory
    if os.path.exists(f"{PROJECT_DIR}/docs"):
        shutil.rmtree(f"{PROJECT_DIR}/docs")

    shutil.copytree(f"{wiki_dir}/build", f"{PROJECT_DIR}/docs")

    run_git_command(["git", "add", f"{PROJECT_DIR}/docs/*"])

    logging.info("Blog post added, builds complete, docs updated.")

    logging.info("Posting message to Telegram")

    app = Client("post_commit")
    app.start()
    try:
        app.send_message(CHANNEL, telegram_message)
    except pyrogram.errors.exceptions.bad_request_400.MessageTooLong:
        telegram_message = build_telegram_message(commit_info, changes, short=True)
        app.send_message(CHANNEL, telegram_message)

    app.edit_message_caption(CHANNEL, 4, build_edit_message())
    app.stop()


main()
