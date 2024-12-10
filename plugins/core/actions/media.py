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

import vlc
import yt_dlp
from ytmusicapi import YTMusic

from data.constants import CONFIG_FILE, PROJECT_FOLDER, CACHING_FOLDER
from utils import *
from api import app

config = load_yaml(CONFIG_FILE)

# vlc
instance = vlc.Instance()
player = instance.media_player_new()
equalizer = vlc.AudioEqualizer()
player.set_equalizer(equalizer)

api = YTMusic()

log = logging.getLogger("module: " + __file__)


def sanitize_filename(filename):
    """
    Sanitize the filename by replacing invalid characters with underscores or removing them.
    """
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    sanitized = sanitized.strip()
    return sanitized


def mpv():
    output = run_stdout("pgrep", "-a", "mpv")
    if output:
        return True
    return False


def play_audio(**kwargs):
    if os.path.exists(kwargs["parameters"]["path"]):
        media = instance.media_new(kwargs["parameters"]["path"])
        player.set_media(media)
        player.play()


def kill_audio(**kwargs):
    if player.get_state() == vlc.State.Playing:
        player.stop()

    if mpv():
        run("pkill", "mpv")


def pause_audio(**kwargs):
    if player.get_state() == vlc.State.Playing:
        player.pause()

    if mpv():
        app.say("The mpv player can be paused in system notifications, sir")


def resume_audio(**kwargs):
    if player.get_state() in [vlc.State.Paused, vlc.State.Stopped]:
        player.play()

    if mpv():
        app.say("The mpv player can be resumed in system notifications, sir")


def mute_volume(**kwargs):
    os.system(f'amixer set Master {kwargs["parameters"]["command"]} > /dev/null 2>&1')


def volume(**kwargs):
    num = find_num_in_list(kwargs["command"])
    current = os.popen('amixer get Master | grep -oP "\[\d+%\]"').read()
    current = int(current.split()[0][1:-2])
    if_up = kwargs["parameters"]["command"] == "up"
    if num:
        if kwargs["parameters"]["command"] == "set":
            os.system(f"amixer set 'Master' {num}% /dev/null 2>&1")
        else:
            os.system(
                f"amixer set 'Master' {current + num if if_up else current - num}% > /dev/null 2>&1")
    else:
        os.system(
            f'amixer set "Master" {current + 25 if if_up else current - 25}% > /dev/null 2>&1')


def save_song(href, title):
    log.info(f"Searching for song named {title}")

    music_folder = f"{CACHING_FOLDER}/music"
    os.makedirs(music_folder, exist_ok=True)

    download = config["plugins"]["core"]["music-download"]
    filename = os.path.join(music_folder, sanitize_filename(title))

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
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if download:
                try:
                    # Fetch video metadata
                    info = ydl.extract_info(href, download=False)
                    file_size = info.get('filesize') or max(
                        f.get('filesize', 0) for f in info.get('formats', []) if f.get('filesize')
                    )

                    # Convert size to MB and skip if greater than 20 MB
                    if file_size and file_size > 20 * 1024 * 1024:
                        log.info(f"Skipping {title} as it exceeds 20 MB.")
                        return None  # Indicate to skip this song

                    # Download the song if it's within size limit
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


def find_song(search):
    result = api.search(search, filter="videos")[0]

    # Check for videoId or fall back to songs if missing
    if not result or not result.get("videoId"):
        result = api.search(search, filter="songs")[0]

    # Return song URL and title if result is valid
    if result and result.get("videoId"):
        song = "https://music.youtube.com/watch?v=" + result["videoId"]
        title = f'{result.get("artists")[0]["name"] if result.get("artists") else "Unknown"} - {result["title"]}'
        return song, title

    return None


def play_song(**kwargs):
    search = ' '.join(kwargs["command"][1:])
    log.info(f"Searching music sources for {search}")
    results = api.search(search, filter="videos")  # Fetch multiple results

    for result in results:
        if not result or not result.get("videoId"):
            continue  # Skip invalid results

        link = "https://music.youtube.com/watch?v=" + result["videoId"]
        title = f'{result.get("artists")[0]["name"] if result.get("artists") else "Unknown"} - {result["title"]}'

        # Attempt to save the song
        song = save_song(link, title)
        if song:  # If song is valid (not skipped), play it
            media = instance.media_new(song)
            player.set_media(media)

            notify(
                title,
                "Playing a requested song",
                10
            )
            player.play()
            return

    app.say("Sorry, I couldn't find a suitable song under 20 MB, sir.")


def boost_bass(**kwargs):
    boost_amount = 4.5

    # Get current amplification levels (assuming these are retrievable)
    current_amp_60hz = equalizer.get_amp_at_index(0)  # 60 Hz (deep bass)
    current_amp_170hz = equalizer.get_amp_at_index(1)  # 170 Hz (bass)
    current_amp_310hz = equalizer.get_amp_at_index(2)  # 310 Hz (upper bass/lower midrange)

    # Increase bass frequencies by the boost amount
    equalizer.set_amp_at_index(current_amp_60hz + boost_amount, 0)  # Boost 60 Hz (deep bass)
    equalizer.set_amp_at_index(current_amp_170hz + boost_amount, 1)  # Boost 170 Hz (bass)
    equalizer.set_amp_at_index(current_amp_310hz + boost_amount, 2)  # Boost 310 Hz (upper bass/lower midrange)

    # Midrange and treble should stay at fixed values (can modify similarly if needed)
    equalizer.set_amp_at_index(0.4, 3)  # 600 Hz (midrange)
    equalizer.set_amp_at_index(0.3, 4)  # 1 kHz (upper midrange)
    equalizer.set_amp_at_index(0.3, 5)  # 3 kHz (high midrange)
    equalizer.set_amp_at_index(0.2, 6)  # 6 kHz (treble)
    equalizer.set_amp_at_index(0.2, 7)  # 12 kHz (upper treble)
    equalizer.set_amp_at_index(0.1, 8)  # 14 kHz (upper treble)
    equalizer.set_amp_at_index(0.1, 9)  # 16 kHz (air)

    # Apply the updated equalizer settings
    player.set_equalizer(equalizer)


def normalize_sound(**kwargs):
    for band in range(10):
        equalizer.set_amp_at_index(0.0, band)

    # Apply the reset equalizer settings to the player
    player.set_equalizer(equalizer)


def find_video(**kwargs):
    html = urllib.request.urlopen(
        f"https://www.youtube.com/results?search_query={urllib.parse.quote('+'.join(kwargs['command'][2:]))}")
    video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
    if video_ids:
        webbrowser.open("https://www.youtube.com/watch?v=" + video_ids[0], autoraise=True)
    else:
        app.say("Sorry, I have not found a matching video, sir, please try again")


def stream(**kwargs):
    link = kwargs["parameters"]["link"]
    process = subprocess.Popen(['mpv', '--shuffle', "--no-video", link], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)

    title = None
    pattern = r'icy-title:\s*([^\n]+)'

    while True:
        # Read output line by line
        output = process.stdout.readline()

        if output == '' and process.poll() is not None:
            break  # Exit loop if process has ended

        if output:
            # Search for the title in the current line of output
            match = re.search(pattern, output)
            if match:
                new_title = match.group(1).strip()

                # Only notify if the title has changed
                if new_title != title:
                    title = new_title
                    notify(
                        title="Streaming audio from a link" if not title else str(title),
                        message=link if not title else "playing a song",
                        timeout=10
                    )
