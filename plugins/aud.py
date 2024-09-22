import os
import logging

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import pygame.mixer

pygame.mixer.init()

log = logging.getLogger("module: " + __file__)

from data.constants import CONFIG_FILE
from utils.utils import yaml_load

config = yaml_load(CONFIG_FILE)

__import__(f"utils.{config['lang']['prefix']}.text")


def play_audio(**kwargs):
    if os.path.exists(kwargs["parameters"]["path"]):
        pygame.mixer.music.load(kwargs["parameters"]["path"])
        pygame.mixer.music.play()


def kill_audio(**kwargs):
    pygame.mixer.music.stop()


def mute_volume(**kwargs):
    os.system(f'amixer set Master {kwargs["parameters"]["command"]} > /dev/null 2>&1')


def volume(**kwargs):
    num = find_num_in_list(kwargs["command"])
    current = os.popen('amixer get Master | grep -oP "\[\d+%\]"').read()
    current = int(current.split()[0][1:-2])
    if num:
        if kwargs["parameters"]["command"] == "set":
            os.system(f"amixer set 'Master' {num}% /dev/null 2>&1")
        else:
            os.system(
                f"amixer set 'Master' {current + num if if_up else current - num}% > /dev/null 2>&1")
    else:
        os.system(
            f'amixer set "Master" {current + 25 if if_up else current - 25}% > /dev/null 2>&1')
