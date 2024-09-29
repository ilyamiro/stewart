import os
import logging
import json
import time
import webbrowser
import re
import urllib
from importlib import import_module

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

from ytmusicapi import YTMusic
import vlc
import yt_dlp

instance = vlc.Instance()
player = instance.media_player_new()
equalizer = vlc.AudioEqualizer()
player.set_equalizer(equalizer)

api = YTMusic()

log = logging.getLogger("module: " + __file__)

from data.constants import CONFIG_FILE, PROJECT_FOLDER
from utils.utils import yaml_load, import_all_from_module, internet, Notify
from audio.output import ttsi

config = yaml_load(CONFIG_FILE)

from utils.en.text import find_num_in_list


def play_audio(**kwargs):
    if os.path.exists(kwargs["parameters"]["path"]):
        media = instance.media_new(kwargs["parameters"]["path"])
        player.set_media(media)
        player.play()


def kill_audio(**kwargs):
    if player.get_state() == vlc.State.Playing:
        player.stop()


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
    log.info(f"searching for song named {title}")

    music_folder = f'{PROJECT_FOLDER}/data/music'
    download = config["command-spec"]["music-download"]

    filename = os.path.join(music_folder, title)

    ydl_opts = {
        'format': 'bestaudio/best',  # Select best quality audio
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',  # Extract audio using ffmpeg
            'preferredcodec': 'mp3',  # Save file as mp3
            'preferredquality': '192',  # Quality of mp3
        }],
        'outtmpl': filename,  # Name of the output file
    }
    # Check if the file already exists
    if os.path.exists(filename + ".mp3"):
        log.info(f"{filename} already exists. Playing the existing file.")
    else:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if download:
                ydl.download([href])
            else:
                formats = ydl.extract_info(href, download=False)["formats"]
                audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get("abr") is not None]

                best_audio = max(audio_formats, key=lambda f: f.get('abr', 0))
                url = best_audio['url']
                log.info(f"Streaming audio from url: {url}")

    return url if not download else filename + ".mp3"


def find_song(search):
    result = api.search(search)[0]
    if result:
        song = "https://music.youtube.com/watch?v=" + result["videoId"]
        title = f'{result.get("artists")[0]["name"] if result.get("artists") else "Unknown"} - {result["title"]}'
        return song, title
    else:
        return None


def play_song(**kwargs):
    search = ' '.join(kwargs["command"][1:])
    log.info(f"Searching music sources for {search}")
    link, title = find_song(search)
    if link:
        song = save_song(link, title)
        media = instance.media_new(song)
        player.set_media(media)

        notification = Notify.Notification.new(
            title,
            "Playing a requested song",
            f"{PROJECT_FOLDER}/data/images/stewart.png"
        )
        notification.set_timeout(8000)
        notification.show()

        player.play()
    else:
        ttsi.say("Sorry, I have not found a matching song, sir, please try again")


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
    html = urllib.request.urlopen(f"https://www.youtube.com/results?search_query={urllib.parse.quote('+'.join(kwargs['command'][2:]))}")
    video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
    if video_ids:
        webbrowser.open("https://www.youtube.com/watch?v=" + video_ids[0], autoraise=True)
    else:
        ttsi.say("Sorry, I have not found a matching video, sir, please try again")
