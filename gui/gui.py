import logging
import os

import flet as ft

from app import App

logger = logging.getLogger("GUI")

DIR = os.path.dirname(os.path.abspath(__file__))


class GUI:
    def __init__(self):
        # self.app = App()
        self.page = None

        self.home = ft.View(controls=[

        ])

        self.navigation = ft.AppBar(
            leading=ft.Image(f"{os.path.dirname(DIR)}/data/images/stewart.png"),
            leading_width=55,
            title=ft.Text("Stewart", size=20),
            actions=[
                ft.IconButton(ft.icons.HOME, on_click=self.change_view, tooltip="Home page", data="home"),
                ft.IconButton(ft.icons.CREATE, tooltip="Create new commands", data="create"),
                ft.IconButton(ft.icons.ACCOUNT_TREE),
                ft.PopupMenuButton(
                    icon=ft.icons.SETTINGS,
                    items=[
                        ft.PopupMenuItem(icon=ft.icons.MIC, text="Voice"),
                        ft.PopupMenuItem(icon=ft.icons.APPS, text="App"),
                        ft.PopupMenuItem(icon=ft.icons.ADD_BOX, text="Plugins"),
                        ft.PopupMenuItem(),
                        ft.PopupMenuItem(icon=ft.icons.CODE, text="For developers"),
                        ft.PopupMenuItem(),
                        ft.PopupMenuItem(icon=ft.icons.INFO, text="About")
                    ]
                )
            ],
            toolbar_height=70


        )

    def start(self, page: ft.Page):
        # initializing a page instance
        self.page = page
        self.page.title = "Stewart"

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


