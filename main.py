import logging
import random
import subprocess
import threading
import os
import time
import sys
import traceback

import utils
from logs import logging_setup, set_logging
from utils import system_setup, admin, clear

log = logging.getLogger("main")

if admin():
    log.error("The app should not be run with super user (sudo or admin) privileges. Exiting. ")
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

# Voice mode: torch must be imported and its BLAS backend initialized BEFORE libmpv / Kokoro threads
# are created (AppAPI). Otherwise the first TorchScript (Silero VAD) call crashes in libopenblas
# (SIGFPE/SIGSEGV). Skipped in text mode to keep that path fast.
if "--text-mode" not in sys.argv:
    try:
        import torch as _torch
        _torch.mm(_torch.ones(8, 8), _torch.ones(8, 8))
    except Exception:
        pass

from app import App
from api import app as iapp

utils.import_utils(iapp.lang, globals())


def trigger_startup_feedback(api, config):
    """Triggers startup sound and voice synthesis as early as possible."""
    startup_cfg = config.get("start-up", {})
    voice_enable = startup_cfg.get("voice-enable", True)
    sound_enable = startup_cfg.get("sound-enable", True)

    sound_path = startup_cfg.get("sound-path", "data/sounds/startup.wav")
    if not os.path.exists(sound_path):
        from data.constants import DEFAULT_DATA_DIR
        candidate = DEFAULT_DATA_DIR / "sounds/startup.wav"
        if candidate.exists():
            sound_path = str(candidate)

    if sound_enable and os.path.exists(sound_path):
        from audio.tts.synthesis import play_audio
        threading.Thread(target=play_audio, args=(sound_path,), daemon=True, name="Startup-Sound").start()
        log.info("Triggered early startup sound")

    if voice_enable:
        answers = startup_cfg.get("answers", [])
        if answers:
            # Prioritize cached audio for instantaneous voice feedback (<2ms)
            cached_list = api.get_cached_answers(answers)
            if cached_list:
                raw_text, parsed_text, wav_path = random.choice(cached_list)
                api.audio.play(wav_path)
                log.info(f"Triggered early startup voice playback: '{parsed_text}'")
            else:
                chosen = random.choice(answers)
                api.say(chosen)
                log.info(f"Triggered early startup voice synthesis: '{chosen}'")


def main():
    try:
        system_setup()
        set_logging(True)

        log.debug("Started running...")

        start_time = time.time()

        app = App(iapp)
        config = app.api.config

        if "--text-mode" in sys.argv:
            config["settings"]["text-mode"] = True

        # Trigger audio and voice feedback at the earliest possible instant
        audio_thread = threading.Thread(
            target=trigger_startup_feedback,
            args=(app.api, config),
            daemon=True,
            name="Startup-Audio"
        )
        audio_thread.start()

        if config["settings"]["text-mode"]:
            from audio.tts.synthesis import TORCH_READY
            TORCH_READY.set()
            app.start(start_time)
            app.run()
        else:
            # Parallelize STT loading with app plugin and command tree initialization
            stt_result = {}

            def init_stt():
                try:
                    from audio.input import STT
                    stt_result["stt"] = STT(app.api.lang)
                except Exception as e:
                    stt_result["error"] = e

            stt_thread = threading.Thread(target=init_stt, daemon=True, name="STT-Init")
            stt_thread.start()

            # Concurrently initialize plugins and command tree on main thread
            app.start(start_time)

            # Wait for STT initialization to complete
            stt_thread.join()

            if "error" in stt_result or "stt" not in stt_result:
                err = stt_result.get("error", "Unknown error")
                log.error(f"Could not initialize speech recognition: {err}. Switching to text mode.")
                from audio.tts.synthesis import TORCH_READY
                TORCH_READY.set()
                config["settings"]["text-mode"] = True
                app.run()
                return

            stt = stt_result["stt"]

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
                    if len(buffer) > 16000:
                        result = stt.check_speaker(buffer)
                        if result:
                            # subprocess.run(["wmctrl", "-a", ""])
                            log.debug("Going out of the sleeping mode")
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

                            log.info("Successfully went into sleeping mode")

                            last_time = time.time()

                    buffer = b""

    except Exception as e:
        log.debug(f"App loop ended with the following error: {e}: \n{traceback.format_exc()} ")


if __name__ == "__main__":
    main()
