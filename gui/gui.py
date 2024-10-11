import logging
import os
from pathlib import Path

import flet as ft

from app import App
from data.constants import PROJECT_FOLDER

logger = logging.getLogger("GUI")


class GUI:
    def change_view(self, e):
        pass

    def __init__(self):
        # self.app = App()
        self.page = None

        self.home = ft.View(controls=[

        ])

        self.navigation = ft.AppBar(
            leading=ft.Image(f"{PROJECT_FOLDER}/data/images/stewart_logo.png"),
            leading_width=210,
            actions=[
                ft.IconButton(ft.icons.HOME, on_click=self.change_view, tooltip="Home page", data="home"),
                ft.IconButton(ft.icons.CREATE, tooltip="Create new commands", data="create"),
                ft.IconButton(ft.icons.ACCOUNT_TREE, tooltip="Command tree"),
                ft.PopupMenuButton(
                    icon=ft.icons.SETTINGS,
                    items=[
                        ft.PopupMenuItem(icon=ft.icons.APPS, text="Configuration"),
                        ft.PopupMenuItem(icon=ft.icons.MIC, text="Audio"),
                        ft.PopupMenuItem(icon=ft.icons.COMPUTER, text="App"),
                        ft.PopupMenuItem(icon=ft.icons.ADD_BOX, text="Plugins"),
                        ft.PopupMenuItem(),
                        ft.PopupMenuItem(icon=ft.icons.CODE, text="For developers"),
                        ft.PopupMenuItem(),
                        ft.PopupMenuItem(icon=ft.icons.INFO, text="About")
                    ]
                )
            ],
            toolbar_height=80

        )

    def start(self, page: ft.Page):
        # initializing a page instance
        self.page = page
        self.page.title = "stewart"

        # setting an unresizable window
        self.page.window.width = 1024
        self.page.window.height = 600
        self.page.window.resizable = False

        # adding app bar
        self.page.appbar = self.navigation

        self.page.update()

        logger.debug("GUI initialization process ended")

        # self.app.start()


def main():
    gui = GUI()
    ft.app(gui.start)


main()
