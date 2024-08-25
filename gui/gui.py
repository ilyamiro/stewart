import logging

import flet as ft

from app import App

logger = logging.getLogger("GUI")


class GUI:
    def __init__(self):
        self.app = None
        self.page = None

    def start(self, page: ft.Page):
        # initializing a page instance
        self.page = page
        self.page.title = "Stewart"

        # setting an unresizable window
        self.page.window.width = 1280
        self.page.window.height = 720
        self.page.window.resizable = False

        self.page.update()

        logger.debug("GUI initialization process ended")

        self.app = App()
        self.app.start()


def main():
    gui = GUI()
    ft.app(gui.start)
