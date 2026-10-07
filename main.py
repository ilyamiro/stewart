import time
PROCESS_START_TIME = time.time()

import logging
import random
import subprocess
import threading
import os
import sys
import traceback

import utils
from logs import logging_setup, set_logging
from utils import system_setup, admin, clear

log = logging.getLogger("main")

if admin():
    log.error("The app should not be run with super user (sudo or admin) privileges. Exiting.")
    sys.exit()


def parse_cli_early():
    if "-h" in sys.argv or "--help" in sys.argv:
        print("""Stewart Voice Assistant

Usage: stewart [OPTIONS]

Options:
  -l, --lang <lang>       Run with specified language code (e.g. 'en', 'ru')
  --set-lang <lang>       Set default language permanently in ~/.config/stewart/lang.txt
  --text-mode             Force text mode input instead of voice recognition
  -v, --version           Show version and exit
  -h, --help              Show this help message and exit

Environment Variables:
  STEWART_LANG            Language override (e.g. STEWART_LANG=en)
  STEWART_CONFIG_DIR      Custom configuration directory
""")
        sys.exit(0)

    if "-v" in sys.argv or "--version" in sys.argv:
        from data.constants import APP_VERSION
        print(f"stewart {APP_VERSION}")
        sys.exit(0)

    for idx, arg in enumerate(sys.argv):
        if arg == "--set-lang" and idx + 1 < len(sys.argv):
            lang = sys.argv[idx + 1].strip().lower()
            from utils.system import set_lang
            path = set_lang(lang)
            print(f"Default language set to '{lang}' ({path})")
            sys.exit(0)
        elif arg.startswith("--set-lang="):
            lang = arg.split("=", 1)[1].strip().lower()
            from utils.system import set_lang
            path = set_lang(lang)
            print(f"Default language set to '{lang}' ({path})")
            sys.exit(0)


parse_cli_early()

from data.constants import PLUGINS_DIR


def check_text_mode_early() -> bool:
    if "--text-mode" in sys.argv:
        return True
    try:
        from pathlib import Path
        for p in [Path.home() / ".config/stewart/config.yaml", Path.home() / ".stewart/config.yaml"]:
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.strip()
                        if stripped.startswith("text-mode:") and "true" in stripped.lower():
                            return True
    except Exception:
        pass
    return False


IS_TEXT_MODE = check_text_mode_early()

if not IS_TEXT_MODE:
    try:
        import torch as _torch
        _torch.mm(_torch.ones(8, 8), _torch.ones(8, 8))
    except Exception:
        pass

from app import App
from api import app as iapp

utils.import_utils(iapp.lang, globals())

STARTUP_AUDIO_DONE = threading.Event()


def trigger_startup_feedback(api, config):
    try:
        startup_cfg = config.get("start-up", {})
        voice_enable = startup_cfg.get("voice-enable", True)
        sound_enable = startup_cfg.get("sound-enable", True)

        sound_path = startup_cfg.get("sound-path", "data/sounds/startup.wav")
        if not os.path.exists(sound_path):
            from data.constants import DEFAULT_DATA_DIR
            candidate = DEFAULT_DATA_DIR / "sounds/startup.wav"
            if candidate.exists():
                sound_path = str(candidate)

        from audio.tts.synthesis import play_audio

        if sound_enable and os.path.exists(sound_path):
            try:
                threading.Thread(target=play_audio, args=(sound_path,), daemon=True, name="StartupSound").start()
            except Exception as e:
                log.warning(f"Startup sound error: {e}")

        if voice_enable:
            answers = startup_cfg.get("answers", [])
            if answers:
                chosen = random.choice(answers)
                cached_wav = api.get_cached_audio_path(chosen)
                if cached_wav and os.path.exists(cached_wav):
                    api.is_speaking = True
                    try:
                        play_audio(cached_wav)
                    finally:
                        api.is_speaking = False
                else:
                    api.say_sync(chosen)
    except Exception as e:
        log.error(f"Error during startup feedback: {e}")
    finally:
        STARTUP_AUDIO_DONE.set()


def main():
    try:
        system_setup()
        set_logging(True)

        start_time = PROCESS_START_TIME
        app = App(iapp)
        config = app.api.config

        if "--text-mode" in sys.argv or IS_TEXT_MODE:
            config["settings"]["text-mode"] = True

        if config["settings"]["text-mode"]:
            from audio.tts.synthesis import TORCH_READY
            TORCH_READY.set()
            app.start(start_time)
            audio_thread = threading.Thread(
                target=trigger_startup_feedback,
                args=(app.api, config),
                daemon=True,
                name="Startup-Audio"
            )
            audio_thread.start()
            app.run()
        else:
            stt_result = {}

            def init_stt():
                try:
                    from audio.input import STT
                    stt = STT(app.api.lang)
                    if hasattr(stt, "wait_ready"):
                        stt.wait_ready(timeout=60)
                    stt_result["stt"] = stt
                except Exception as e:
                    stt_result["error"] = e

            stt_thread = threading.Thread(target=init_stt, daemon=True, name="STT-Init")
            stt_thread.start()

            app.start(start_time)

            audio_thread = threading.Thread(
                target=trigger_startup_feedback,
                args=(app.api, config),
                daemon=True,
                name="Startup-Audio"
            )
            audio_thread.start()

            stt_thread.join()

            if "error" in stt_result or "stt" not in stt_result:
                from audio.tts.synthesis import TORCH_READY
                TORCH_READY.set()
                config["settings"]["text-mode"] = True
                app.run()
                return

            stt = stt_result["stt"]

            STARTUP_AUDIO_DONE.wait(timeout=15)

            if hasattr(stt, "flush"):
                stt.flush()

            if config["settings"]["animation"]:
                from gui.animation import animation
                thread = threading.Thread(target=animation)
                thread.daemon = True
                thread.start()

            app.run(stt, None)

            last_time = time.time()
            buffer = b""
            while True:
                data = stt.stream.read(512, exception_on_overflow=False)
                if stt.vad(data):
                    buffer += data
                else:
                    if len(buffer) > 6000:
                        result = stt.check_speaker(buffer)
                        if result:
                            elapsed_time = time.time() - last_time
                            if elapsed_time < 600:
                                app.api.say(random.choice(config["answers"]["default"]))
                            elif elapsed_time < 3600:
                                app.api.say(random.choice(config["answers"]["short_away"]))
                            elif elapsed_time < 7200:
                                app.api.say(random.choice(config["answers"]["under_hour"]))
                            elif elapsed_time < 21600:
                                app.api.say(random.choice(config["answers"]["over_hour"]))
                            elif elapsed_time < 43200:
                                app.api.say(random.choice(config["answers"]["multiple_hours"]))
                            else:
                                app.api.say(random.choice(config["answers"]["half_day"]))

                            app.run(stt, last_time)
                            last_time = time.time()

                    buffer = b""

    except Exception as e:
        log.debug(f"App loop ended with error: {e}: \n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
