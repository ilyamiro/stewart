import logging
import os
import random
import signal
import threading
import time
from pathlib import Path

import flet as ft

from utils import track_time, tracker, remove_non_letters
from data.constants import PROJECT_FOLDER

from gui.components.objects import *

log = logging.getLogger("GUI")

# disable gui library logs
logging.getLogger("flet_core").setLevel(logging.ERROR)
logging.getLogger("flet").setLevel(logging.ERROR)
logging.getLogger("flet_runtime").setLevel(logging.ERROR)


class GUI:
    def __init__(self, start_time):
        self.start_time = start_time

        self.checking_tracker = None
        self.checking_stt = None

        self.page = None

        # set events
        send_button.on_click = self.send_message
        input_field.on_submit = self.send_message
        mic_button.on_click = self.pause_stt

    # <! ---------------------- Small functions ---------------------- !>
    # def animate(self, obj):
    #     frames = [
    #         " 🌍 ",
    #         " 🌎 ",
    #         " 🌏 ",
    #         " 🌍 ",
    #         " 🌎 ",
    #         " 🌏 "
    #     ]
    #
    #     # def animate_in():
    #     while not tracker.get_value():
    #         for char in frames:
    #             obj.value = "Processing " + char
    #             time.sleep(0.2)
    #             self.page.update()
    #
    #     # thread = threading.Thread(target=animate_in)
    #     # thread.start()

    def cprint(self, obj, text):
        for letter in text:
            obj.value = obj.value + letter
            time.sleep(0.03)
            self.page.update()

    def listener(self, obj):
        while self.checking_tracker:
            if tracker.get_value() != tracker.value[0]:
                obj.value = "##### "
                self.cprint(obj, tracker.get_value())
                break

    def pause_stt(self, e=None):
        if self.app.stt.stream.is_active():
            self.app.stt.stream.stop_stream()
            mic_button.icon_color = PURPLE
            mic_button.bgcolor = ft.colors.TRANSPARENT
        else:
            self.app.stt.stream.start_stream()
            mic_button.icon_color = "white"
            mic_button.bgcolor = PURPLE

        mic_button.update()

    # <! ---------------------- Major functions ---------------------- !>

    def change_view(self, e):
        pass

    def send_message(self, e):
        user_input = input_field.value.strip()
        input_field.value = ""
        input_field.focus()
        if user_input:
            self.app.process_trigger_no_voice(user_input)

    def process_message_stt_callback(self, new_value):
        self.checking_tracker = False

        # add person row
        person_row = PersonRow(new_value)
        chat_messages.controls.append(
            person_row
        )
        self.page.update()

        # add answer row
        va_row = AnswerRow()
        chat_messages.controls.append(
            va_row
        )
        self.page.update()

        self.checking_tracker = True
        thread = threading.Thread(target=self.listener, args=(va_row.controls[0].title,))
        thread.start()

    # <! ---------------------- Start ---------------------- !>

    def start(self, page: ft.Page):
        # initializing a page instance
        self.page = page
        self.page.title = "stewart"

        # setting an unresizable window
        self.page.window.width = 1024
        self.page.window.height = 625
        self.page.window.resizable = False

        # adding loading view
        self.page.views.append(loading_view)
        self.page.update()

        log.debug("GUI initialization process ended")

        # <! ------------------- app initialization ------------------- !>
        from app import App
        from api import app as app_api
        from api import tree

        self.app = App(app_api, tree)

        self.app.start(self.start_time)
        self.app.stt.stream.stop_stream()

        self.page.views.pop()
        self.page.views.append(home_view)

        self.page.update()

        self.app.request_monitor.set_callback(self.process_message_stt_callback)

        self.app.run()


