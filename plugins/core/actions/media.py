import os
import re
import time
import json
import logging
import urllib.request
import urllib.parse
import webbrowser
import subprocess
import shutil
import functools
from importlib import import_module

from data.constants import CONFIG_FILE, PROJECT_DIR
from utils import *
from api import app

import_utils(app.lang, globals())

_api_ytmusic = None

def _get_ytmusic():
    global _api_ytmusic
    if _api_ytmusic is None:
        from ytmusicapi import YTMusic
        _api_ytmusic = YTMusic()
    return _api_ytmusic

log = logging.getLogger("module: " + __file__)

@functools.lru_cache(maxsize=32)
def _which(cmd):
    return shutil.which(cmd)

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
    cmd = kwargs["command"].parameters.get("command", "toggle")
    if _which("wpctl"):
        val = "1" if cmd == "mute" else ("0" if cmd == "unmute" else "toggle")
        subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", val], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if _which("pactl"):
        val = "1" if cmd == "mute" else ("0" if cmd == "unmute" else "toggle")
        subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", val], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if _which("amixer"):
        subprocess.run(["amixer", "set", "Master", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def volume(**kwargs):
    results = find_num(kwargs["context"])
    num = results[0] if results else None
    command = kwargs["command"].parameters.get("command", "set")
    adjustment = num if num is not None else 25

    if _which("wpctl"):
        if command == "set" and num is not None:
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{num}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log.info(f"Set volume to {num}% via wpctl")
        elif command == "up":
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{adjustment}%+"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log.info(f"Increased volume by {adjustment}% via wpctl")
        elif command == "down":
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{adjustment}%-"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log.info(f"Decreased volume by {adjustment}% via wpctl")
        return

    if _which("pactl"):
        if command == "set" and num is not None:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{num}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log.info(f"Set volume to {num}% via pactl")
        elif command == "up":
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{adjustment}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif command == "down":
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{adjustment}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    if _which("amixer"):
        try:
            current_raw = os.popen('amixer get Master | grep -oP "\\[\\d+%\\]"').read().split()
            current = int(current_raw[0][1:-2]) if current_raw else 50
        except Exception:
            current = 50
        new_volume = current + adjustment if command == "up" else current - adjustment
        new_volume = max(0, min(100, new_volume))
        target = num if (command == "set" and num is not None) else new_volume
        os.system(f"amixer set 'Master' {target}% > /dev/null 2>&1")
        log.info(f"Set system volume to {target}% via amixer")


def save_song(href, title):
    log.info(f"Searching for a song named {title}")

    music_folder = app.runtime.mkdir_cache("music")
    app.runtime.cleanup(music_folder, max_files=25)
    download = app.config["plugins"]["core"]["music-download"]

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

    if os.path.exists(filename + ".mp3"):
        log.info(f"{filename} already exists. Playing the existing file.")
    else:
        import yt_dlp
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
                    log.info(f"Downloading an audio file from {href} into a file")

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
    results = _get_ytmusic().search(search, filter="videos")

    for result in results:
        if not result or not result.get("videoId"):
            continue
        link = "https://music.youtube.com/watch?v=" + result["videoId"]
        title = f'{result.get("artists")[0]["name"] if result.get("artists") else "Unknown"} - {result["title"]}'

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


