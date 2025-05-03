from pathlib import Path
import subprocess
import re
import logging
from pyrogram import Client

from translate_commit import process

logging.basicConfig(level=logging.INFO)

PROJECT_FOLDER = Path(__file__).resolve().parent.parent.parent
CHANNEL = "@stewart_github"
REPO_URL = "https://github.com/ilyamiro/stewart"

with open(f"{PROJECT_FOLDER}/version.txt", "r", encoding="utf-8") as file:
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


def build_telegram_message(commit_info, changes):
    return f"""**Новый коммит** 
Версия: **{version}**
    
Репозиторий: **{commit_info["repository"]}**
Ветка: **{commit_info['branch']}**

Автор: **{commit_info['author']}**
Дата: **{commit_info['date']}**

{commit_info['message']}

{changes}

**[Cсылка на коммит]({REPO_URL}/commit/{commit_info['hash']})**

__автоматически сгенерированное сообщение__
"""


def build_edit_message():
    return f"""Всем привет!

Меня зовут Илья, я 17 летний разработчик

В этом телеграм канале я буду показывать свой прогресс в создании помощника по имени Стюарт. Я буду постить мой прогресс, дневные задачи и прогресс на русском и английском языках

Текущая версия ассистента: **{version}**

GitHub: https://github.com/ilyamiro/Stewart
YouTube: https://youtube.com/@stewart.github

Мой телеграм: http://t.me/sacrificeit
"""


def get_commit_info():
    commit_info = {
        'message': process(run_git_command(['git', 'log', '-1', '--pretty=%B'])),
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


def main():
    commit_info = get_commit_info()
    if not commit_info['message'].startswith("v"):
        logging.info("No new version commit detected, exiting.")
        return

    changes = get_commit_changes(commit_info['hash'])

    telegram_message = build_telegram_message(commit_info, changes)
    logging.info("Posting message to Telegram")

    app = Client("post_commit")
    app.start()
    app.send_message(CHANNEL, telegram_message)
    app.edit_message_caption(CHANNEL, 4, build_edit_message())
    app.stop()


main()
