import random
import subprocess
import time
import requests
from bs4 import BeautifulSoup
import lxml

from api import app
from data.constants import PLUGINS_DIR
from utils import run


def move():
    WINDOW_KEYWORD = "Zen Browser"  # Part of window title or class
    MONITOR_POSITIONS = [(0, 0), (1920, 0)]  # Example: two monitors, second starts at x=1920
    TARGET_MONITOR = 1  # Index of target monitor (0-based)

    def list_windows():
        result = subprocess.run(["wmctrl", "-lx"], capture_output=True, text=True)
        return result.stdout.splitlines()

    def find_window(keyword):
        for line in list_windows():
            if keyword.lower() in line.lower():
                parts = line.split()
                win_id = parts[0]
                return win_id
        return None

    def move_window(win_id, x, y):
        subprocess.run(["wmctrl", "-i", "-r", win_id, "-e", f"0,{x},{y},-1,-1"])

    print("Waiting for window to appear...")
    while True:
        win_id = find_window(WINDOW_KEYWORD)
        if win_id:
            print(f"Window found: {win_id}, moving it...")
            x, y = MONITOR_POSITIONS[TARGET_MONITOR]
            move_window(win_id, x, y)
            break
        time.sleep(0.25)


def ultrakill(**kwargs):
    # app.say("Добро пожаловать, сэр. Я подготовил для вас интересное занятие к вашему возращению.")
    subprocess.run([
        "gsettings",
        "set",
        "org.gnome.desktop.background",
        "picture-uri-dark",
        "file:///home/ilyamiro/Изображения/Wallpapers/wallpaper_black.jpg"
    ])
    subprocess.run(
        ["sudo", "tee", "/sys/class/leds/asus::kbd_backlight/brightness"],
        input="0\n",
        text=True
    )
    
    subprocess.run(["wmctrl", "-k", "on"])

    subprocess.Popen(["bottles-cli", "run", "-b", "game", "-p", "ULTRAKILL"])

    subprocess.Popen(["alacritty", "-e", "cava"])

    app.audio.play(f"{PLUGINS_DIR}/custom/actions/ultra.mp3")

    move()


app.add_func_for_search(ultrakill)

app.manager.add(
    app.Command(
        keywords=["кого", "я", "обманываю"],
        action="ultrakill",
        tts=True,
        responses=[]
    )
)


def csgo(**kwargs):
    app.say("Запускаю игру, сэр")

    subprocess.run(["xrandr", "--output", "eDP", "--mode", "1280x1024", "--set", "scaling mode", "Full"])

    subprocess.Popen(["steam", "-applaunch", "730", "-console",  "-exec", "autoexec"])

    time.sleep(15)

    app.say("Я подключил вас к серверам киберш+ок для разминки. Удачной игры, сэр!")


app.add_func_for_search(csgo)


app.manager.add(
    app.Command(
        keywords=["запусти", "контр", "страйк"],
        action="csgo",
        tts=True,
        responses=[],
        synonyms={
            "запусти": ["открой", ]
        }
    )
)


def home1():
    app.say("С возвращением, сэр! Добро пожаловать домой. Хотите ли вы чтобы я включил музыку?")
    subprocess.run(
        ["sudo", "tee", "/sys/class/leds/asus::kbd_backlight/brightness"],
        input="3\n",
        text=True
    )
    subprocess.run(["wmctrl", "-k", "on"])
    subprocess.run(["brightnessctl", "set", "100%"])
    subprocess.Popen(["bash", "/home/ilyamiro/Документы/pycharm-community-2023.2.3/bin/pycharm.sh"])
    subprocess.Popen(["xdg-open", "https://ilyamiro.github.io/stewart/docs/Getting%20Started"])
    move()


def home2():
    link = "https://fluxfm.streamabc.net/flx-chillhop-mp3-128-8581707?sABC=6825027p%230%233n1o17opo5312o497o69212842qq72s8%23fgernzf.syhksz.qr&aw_0_1st.playerid=streams.fluxfm.de&amsparams=playerid:streams.fluxfm.de;skey:1747255932"
    app.audio.stream(link)


home_scenario = app.Scenario("home", app.Timeline([
    [
        app.Trigger(
            ["я", "дома"],
            home1,
        )
    ],
    [
        app.Trigger(
            ["давай"],
            home2

        )
    ]
]), max_gap=3)
app.add_scenario(home_scenario)


