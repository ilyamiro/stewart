import os
import re
import time
import json
import logging
import urllib.request
import urllib.parse
import webbrowser
import subprocess
from importlib import import_module

import yt_dlp
from ytmusicapi import YTMusic

from data.constants import CONFIG_FILE, PROJECT_DIR
from utils import *
from api import app

import_utils(app.lang, globals())

config = load_yaml(CONFIG_FILE)

api_ytmusic = YTMusic()

log = logging.getLogger("module: " + __file__)

boost_amount = 0.5


def play_audio(**kwargs):
    if os.path.exists(kwargs["command"].parameters["path"]):
        app.audio.play(kwargs["command"].parameters["path"])


def kill_audio(**kwargs):
    app.audio.stop()


def pause_audio(**kwargs):
    app.audio.player.pause = True


def resume_audio(**kwargs):
    app.audio.player.pause = False


def mute_volume(**kwargs):
    os.system(f'amixer set Master {kwargs["command"].parameters["command"]} > /dev/null 2>&1')


def volume(**kwargs):
    results = find_num(kwargs["context"])
    if results:
        num = results[0]
    else:
        num = None

    command = kwargs["command"].parameters["command"]
    current = int(os.popen('amixer get Master | grep -oP "\[\d+%\]"').read().split()[0][1:-2])
    adjustment = num if num else 25
    new_volume = current + adjustment if command == "up" else current - adjustment

    if command == "set" and num:
        os.system(f"amixer set 'Master' {num}% > /dev/null 2>&1")
        log.info(f"Set system volume to {num}")
    else:
        os.system(f"amixer set 'Master' {new_volume}% > /dev/null 2>&1")
        log.info(f"Set system volume to {new_volume}")


def save_song(href, title):
    log.info(f"Searching for a song named {title}")

    music_folder = app.runtime.mkdir_cache("music")
    app.runtime.cleanup(music_folder, max_files=25)
    download = config["plugins"]["core"]["music-download"]

    filename = os.path.join(music_folder, sanitize_filename(title))
    max_file_size = 20 * 1024 * 1024
    url = None

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': filename,
    }

    if os.path.exists(filename + ".mp3") and download:
        log.info(f"{filename} already exists. Playing the existing file.")
    else:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if download:
                try:
                    info = ydl.extract_info(href, download=False)
                    file_size = info.get('filesize') or max(
                        f.get('filesize', 0) for f in info.get('formats', []) if f.get('filesize')
                    )

                    if file_size and file_size > max_file_size:
                        log.info(f"Skipping {title} as it exceeds 20 MB.")
                        return None

                    ydl.download([href])

                except Exception as e:
                    log.error(f"Failed to download song {title}: {str(e)}")
                    return None
            else:
                formats = ydl.extract_info(href, download=False)["formats"]
                audio_formats = [f for f in formats if
                                 f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get("abr") is not None]

                best_audio = max(audio_formats, key=lambda f: f.get('abr', 0))
                url = best_audio['url']
                log.info(f"Streaming audio from url: {url}")

    return url if not download else filename + ".mp3"


def play_song(**kwargs):
    search = kwargs["context"]
    log.info(f"Searching music sources for {search}")
    results = api_ytmusic.search(search, filter="songs")  # Fetch multiple results

    for result in results:
        if not result or not result.get("videoId"):
            continue  # Skip invalid results

        link = "https://music.youtube.com/watch?v=" + result["videoId"]
        title = f'{result.get("artists")[0]["name"] if result.get("artists") else "Unknown"} - {result["title"]}'

        # Attempt to save the song
        song = save_song(link, title)
        if song:
            notify(
                title,
                "Playing a requested song" if app.lang == "en" else "Воспроизведение запрошенной песни",
                8
            )
            if song.startswith("https"):
                app.audio.stream(song)
            else:
                app.audio.play(song)
            return

    if app.lang == "en":
        app.say("Sorry, I couldn't find a suitable song under twenty megabytes, sir.")
    if app.lang == "ru":
        app.say("Извините, сэр, я не смог найти подходящую песню весом меньше двадцати мегабайт")


def boost_bass(**kwargs):
    bass_boost_bands = [band.copy() for band in app.audio.equalizer_values]
    for band in bass_boost_bands:
        if band['frequency'] in [30, 40, 50, 60, 70, 80]:
            band['gain'] += boost_amount

    app.audio.update_equalizer(bass_boost_bands)


def normalize_sound(**kwargs):
    app.audio.update_equalizer()


def find_video(**kwargs):
    html = urllib.request.urlopen(
        f"https://www.youtube.com/results?search_query={urllib.parse.quote(kwargs['context'])}")
    video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
    if video_ids:
        webbrowser.open("https://www.youtube.com/watch?v=" + video_ids[0], autoraise=True)
    else:
        if app.lang == "en":
            app.say("Sorry, I have not found a matching video, sir, please try again")
        elif app.lang == "ru":
            app.say("Извините, сэр, я не смог найти подходящее видео, пожалуйста, попробуйте снова.")


def find(**kwargs):
    to_find = kwargs.get("context")
    if app.lang == "en":
        app.say("That's what I could find for " + to_find)
    elif app.lang == "ru":
        app.say("Вот что мне удалось найти по запросу " + to_find)

    encoded_query = urllib.parse.quote(to_find)

    if any(i in to_find for i in ["youtube", "ютуб"]):
        webbrowser.open("https://www.youtube.com/results?search_query=" + encoded_query, autoraise=True)
    else:
        webbrowser.open("https://www.google.com/search?q=" + encoded_query, autoraise=True)


def find_open(**kwargs):
    find_link(kwargs.get("context"))


def stream(**kwargs):
    link = kwargs["command"].parameters["link"]
    app.audio.stream(link)


