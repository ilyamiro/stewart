import os
import logging

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import pygame.mixer

pygame.mixer.init()

log = logging.getLogger("module: " + __file__)


def play_audio(**kwargs):
    if os.path.exists(kwargs["parameters"]["path"]):
        pygame.mixer.music.load(kwargs["parameters"]["path"])
        pygame.mixer.music.play()


def kill_audio(**kwargs):
    pygame.mixer.music.stop()
