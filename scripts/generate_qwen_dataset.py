#!/usr/bin/env python3
"""
Synthetic Training Dataset Generator for Stewart Tool Calling (Qwen2.5-0.5B).
Generates thousands of realistic, diverse, multi-lingual (EN/RU) examples
mapped to Stewart's tool calling schemas.
"""

import json
import random
from pathlib import Path
from typing import List, Dict, Any

# Define Stewart Tool Schemas for Qwen
STEWART_TOOLS = [
    {
        "name": "media_control",
        "description": "Control music and media playback (pause, resume, skip track, previous song, mute).",
        "parameters": {
            "type": "object",
            "properties": {
                "control": {
                    "type": "string",
                    "enum": ["play-pause", "next", "previous", "stop", "mute", "unmute"],
                    "description": "Playback action to perform"
                },
                "context": {
                    "type": "string",
                    "description": "Optional media details or search query"
                }
            },
            "required": ["control"]
        }
    },
    {
        "name": "volume",
        "description": "Adjust or set master system volume level.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["up", "down", "set", "mute", "unmute"],
                    "description": "Volume direction or action"
                },
                "context": {
                    "type": "string",
                    "description": "Amount, percentage or specific volume level (e.g. '50%', '10', 'maximum')"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "brightness",
        "description": "Adjust or set screen display brightness.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["up", "down", "set"],
                    "description": "Brightness direction or action"
                },
                "context": {
                    "type": "string",
                    "description": "Percentage or level (e.g. '80%', 'max', 'minimum')"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "tell_time",
        "description": "Announce the current system time or date.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Optional format request (e.g. 'date', 'time', 'exact')"
                }
            }
        }
    },
    {
        "name": "say_weather",
        "description": "Fetch and announce the current weather forecast.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Optional city name or location"
                }
            }
        }
    },
    {
        "name": "timer",
        "description": "Set, start or cancel a countdown timer.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Timer duration (e.g. '5 minutes', '30 seconds', '1 hour', '10 мин')"
                },
                "action": {
                    "type": "string",
                    "enum": ["set", "cancel", "status"],
                    "default": "set"
                }
            },
            "required": ["context"]
        }
    },
    {
        "name": "stopwatch",
        "description": "Control stopwatch (start, stop, reset, lap).",
        "parameters": {
            "type": "object",
            "properties": {
                "way": {
                    "type": "string",
                    "enum": ["on", "off", "reset", "lap"],
                    "description": "Stopwatch operation"
                }
            },
            "required": ["way"]
        }
    },
    {
        "name": "hotkey",
        "description": "Simulate keyboard shortcut or window management hotkey.",
        "parameters": {
            "type": "object",
            "properties": {
                "hotkey": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key combination list, e.g. ['ctrl', 'w'] to close tab, ['ctrl', 't'] for new tab, ['alt', 'f4'] to close window"
                },
                "context": {
                    "type": "string",
                    "description": "Target description"
                }
            },
            "required": ["hotkey"]
        }
    },
    {
        "name": "subprocess",
        "description": "Launch or open a desktop application (file manager, terminal, browser, text editor).",
        "parameters": {
            "type": "object",
            "properties": {
                "subprocess": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Application command to execute, e.g. ['xdg-open', '.'] or ['nautilus'] or ['google-chrome']"
                },
                "context": {
                    "type": "string",
                    "description": "File or folder name or app name"
                }
            },
            "required": ["subprocess"]
        }
    },
    {
        "name": "screenshot",
        "description": "Capture a screenshot of the entire screen or active window.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Optional area specification ('full', 'window', 'selection')"
                }
            }
        }
    },
    {
        "name": "lock_session",
        "description": "Lock the user session or screen immediately.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "battery_health",
        "description": "Report current battery state, percentage, and health status.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "play_song",
        "description": "Search and play a specific song, artist, or music track on YouTube/YouTube Music.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Song title or artist query"
                }
            },
            "required": ["context"]
        }
    },
    {
        "name": "find_video",
        "description": "Search and open a video on YouTube.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Search phrase or topic for the video"
                }
            },
            "required": ["context"]
        }
    },
    {
        "name": "typing",
        "description": "Type text directly into the focused window via keyboard emulation.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Text to type out"
                }
            },
            "required": ["context"]
        }
    }
]

# Prefixes for natural human phrasing
EN_PREFIXES = [
    "", "please ", "stewart ", "hey stewart ", "stewart please ", "could you ", "can you please ",
    "would you mind to ", "go ahead and ", "just ", "quick question ", "hey "
]
RU_PREFIXES = [
    "", "пожалуйста ", "стюарт ", "стюарт пожалуйста ", "эй стюарт ", "можешь ", "сделай ",
    "будь добр ", "пожалуйста сделай ", "давай ", "просто "
]


def generate_samples() -> List[Dict[str, Any]]:
    samples = []

    # 1. MEDIA CONTROL
    media_patterns = [
        # play-pause
        ("pause the music", "media_control", {"control": "play-pause"}),
        ("pause playback", "media_control", {"control": "play-pause"}),
        ("pause video", "media_control", {"control": "play-pause"}),
        ("unpause the song", "media_control", {"control": "play-pause"}),
        ("resume playback", "media_control", {"control": "play-pause"}),
        ("resume music", "media_control", {"control": "play-pause"}),
        ("stop the music", "media_control", {"control": "play-pause"}),
        ("halt audio", "media_control", {"control": "play-pause"}),
        ("поставь на паузу", "media_control", {"control": "play-pause"}),
        ("пауза музыки", "media_control", {"control": "play-pause"}),
        ("останови воспроизведение", "media_control", {"control": "play-pause"}),
        ("возобнови музыку", "media_control", {"control": "play-pause"}),
        ("продолжи воспроизведение", "media_control", {"control": "play-pause"}),
        ("сними с паузы", "media_control", {"control": "play-pause"}),
        # next
        ("skip this track", "media_control", {"control": "next"}),
        ("next song", "media_control", {"control": "next"}),
        ("next track please", "media_control", {"control": "next"}),
        ("play the next one", "media_control", {"control": "next"}),
        ("следующий трек", "media_control", {"control": "next"}),
        ("следующая песня", "media_control", {"control": "next"}),
        ("переключи на следующий", "media_control", {"control": "next"}),
        ("скипни песню", "media_control", {"control": "next"}),
        ("включи следующую песню", "media_control", {"control": "next"}),
        # previous
        ("previous song", "media_control", {"control": "previous"}),
        ("previous track", "media_control", {"control": "previous"}),
        ("go back to last song", "media_control", {"control": "previous"}),
        ("предыдущий трек", "media_control", {"control": "previous"}),
        ("предыдущая песня", "media_control", {"control": "previous"}),
        ("включи песню назад", "media_control", {"control": "previous"}),
        ("верни прошлую песню", "media_control", {"control": "previous"}),
        # mute/unmute
        ("mute the sound", "media_control", {"control": "mute"}),
        ("unmute audio", "media_control", {"control": "unmute"}),
        ("заглуши звук", "media_control", {"control": "mute"}),
        ("выключи звук в плеере", "media_control", {"control": "mute"}),
    ]
    for text, tool, args in media_patterns:
        prefixes = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in prefixes:
            samples.append({"query": f"{p}{text}".strip(), "tool": tool, "args": args})

    # 2. VOLUME
    vol_steps = ["5", "10", "15", "20", "25", "50", "75", "100", "30%", "60%", "max"]
    for step in vol_steps:
        samples.append({"query": f"set volume to {step}", "tool": "volume", "args": {"command": "set", "context": step}})
        samples.append({"query": f"put volume at {step}", "tool": "volume", "args": {"command": "set", "context": step}})
        samples.append({"query": f"volume {step}", "tool": "volume", "args": {"command": "set", "context": step}})
        samples.append({"query": f"установи громкость на {step}", "tool": "volume", "args": {"command": "set", "context": step}})
        samples.append({"query": f"громкость {step}", "tool": "volume", "args": {"command": "set", "context": step}})
        samples.append({"query": f"сделай громкость {step}", "tool": "volume", "args": {"command": "set", "context": step}})

    vol_variations = [
        ("make it louder", "volume", {"command": "up", "context": "10"}),
        ("turn up the sound", "volume", {"command": "up", "context": "10"}),
        ("volume up", "volume", {"command": "up", "context": "10"}),
        ("increase the volume a bit", "volume", {"command": "up", "context": "10"}),
        ("boost audio", "volume", {"command": "up", "context": "10"}),
        ("turn the sound down", "volume", {"command": "down", "context": "10"}),
        ("volume down", "volume", {"command": "down", "context": "10"}),
        ("make it quieter", "volume", {"command": "down", "context": "10"}),
        ("decrease volume", "volume", {"command": "down", "context": "10"}),
        ("lower the sound", "volume", {"command": "down", "context": "10"}),
        ("сделай погромче", "volume", {"command": "up", "context": "10"}),
        ("прибавь звук", "volume", {"command": "up", "context": "10"}),
        ("увеличь громкость", "volume", {"command": "up", "context": "10"}),
        ("погромче пожалуйста", "volume", {"command": "up", "context": "10"}),
        ("сделай тише", "volume", {"command": "down", "context": "10"}),
        ("убавь громкость", "volume", {"command": "down", "context": "10"}),
        ("потише звук", "volume", {"command": "down", "context": "10"}),
        ("уменьши звук", "volume", {"command": "down", "context": "10"}),
        ("mute all sound", "volume", {"command": "mute", "context": ""}),
        ("выключи звук полностью", "volume", {"command": "mute", "context": ""}),
    ]
    for text, tool, args in vol_variations:
        prefixes = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in prefixes:
            samples.append({"query": f"{p}{text}".strip(), "tool": tool, "args": args})

    # 3. BRIGHTNESS
    bright_variations = [
        ("screen brightness up", "brightness", {"command": "up", "context": "10"}),
        ("increase display brightness", "brightness", {"command": "up", "context": "10"}),
        ("make display brighter", "brightness", {"command": "up", "context": "10"}),
        ("make screen darker", "brightness", {"command": "down", "context": "10"}),
        ("dim the screen", "brightness", {"command": "down", "context": "10"}),
        ("lower display brightness", "brightness", {"command": "down", "context": "10"}),
        ("прибавь яркость экрана", "brightness", {"command": "up", "context": "10"}),
        ("сделай экран поярче", "brightness", {"command": "up", "context": "10"}),
        ("увеличь яркость", "brightness", {"command": "up", "context": "10"}),
        ("сделай потемнее экран", "brightness", {"command": "down", "context": "10"}),
        ("убавь яркость дисплея", "brightness", {"command": "down", "context": "10"}),
        ("потусклее экран", "brightness", {"command": "down", "context": "10"}),
    ]
    for text, tool, args in bright_variations:
        prefixes = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in prefixes:
            samples.append({"query": f"{p}{text}".strip(), "tool": tool, "args": args})

    for val in ["50%", "70%", "100%", "30%", "maximum", "max"]:
        samples.append({"query": f"set brightness to {val}", "tool": "brightness", "args": {"command": "set", "context": val}})
        samples.append({"query": f"поставь яркость на {val}", "tool": "brightness", "args": {"command": "set", "context": val}})

    # 4. TELL TIME & DATE
    time_variations = [
        "what time is it", "what is the current time", "tell me the time", "do you know what time it is",
        "current time please", "what time do we have", "what hour is it", "tell me the exact time",
        "сколько сейчас времени", "который час", "подскажи время", "сколько времени", "скажи точное время",
        "какое сейчас время", "назови текущее время", "время скажи", "который сейчас час"
    ]
    for text in time_variations:
        prefixes = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in prefixes:
            samples.append({"query": f"{p}{text}".strip(), "tool": "tell_time", "args": {}})

    # 5. WEATHER
    weather_cities = ["", " in London", " in Paris", " in Berlin", " in Tokyo", " in Moscow", " в Москве", " в Петербурге"]
    weather_phrases = [
        "what is the weather like", "how is the weather outside", "tell me the weather forecast",
        "is it raining outside", "what is the temperature today", "check the weather",
        "какая сейчас погода", "какая погода на улице", "скажи прогноз погоды", "будет ли сегодня дождь",
        "погода за окном", "что там с погодой"
    ]
    for text in weather_phrases:
        prefixes = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in prefixes[:6]:
            for city in weather_cities[:3]:
                ctx = city.replace(" in ", "").replace(" в ", "").strip()
                samples.append({"query": f"{p}{text}{city}".strip(), "tool": "say_weather", "args": {"context": ctx} if ctx else {}})

    # 6. TIMER
    timer_durations = [
        ("1 minute", "1 minute"), ("2 minutes", "2 minutes"), ("5 minutes", "5 minutes"),
        ("10 minutes", "10 minutes"), ("15 minutes", "15 minutes"), ("20 minutes", "20 minutes"),
        ("30 minutes", "30 minutes"), ("45 minutes", "45 minutes"), ("1 hour", "1 hour"),
        ("30 seconds", "30 seconds"), ("15 seconds", "15 seconds"),
        ("1 минуту", "1 минута"), ("5 минут", "5 минут"), ("10 минут", "10 минут"),
        ("15 минут", "15 минут"), ("20 минут", "20 минут"), ("30 минут", "30 минут"),
        ("1 час", "1 час"), ("45 секунд", "45 секунд"), ("полчаса", "30 минут")
    ]
    for dur_phrase, dur_norm in timer_durations:
        samples.append({"query": f"set a timer for {dur_phrase}", "tool": "timer", "args": {"context": dur_norm, "action": "set"}})
        samples.append({"query": f"start timer for {dur_phrase}", "tool": "timer", "args": {"context": dur_norm, "action": "set"}})
        samples.append({"query": f"timer {dur_phrase}", "tool": "timer", "args": {"context": dur_norm, "action": "set"}})
        samples.append({"query": f"поставь таймер на {dur_phrase}", "tool": "timer", "args": {"context": dur_norm, "action": "set"}})
        samples.append({"query": f"запусти таймер на {dur_phrase}", "tool": "timer", "args": {"context": dur_norm, "action": "set"}})
        samples.append({"query": f"таймер {dur_phrase}", "tool": "timer", "args": {"context": dur_norm, "action": "set"}})

    # 7. STOPWATCH
    stopwatch_phrases = [
        ("start stopwatch", {"way": "on"}),
        ("launch stopwatch", {"way": "on"}),
        ("turn on stopwatch", {"way": "on"}),
        ("stop stopwatch", {"way": "off"}),
        ("pause stopwatch", {"way": "off"}),
        ("halt the stopwatch", {"way": "off"}),
        ("reset stopwatch", {"way": "reset"}),
        ("запусти секундомер", {"way": "on"}),
        ("включи секундомер", {"way": "on"}),
        ("останови секундомер", {"way": "off"}),
        ("выключи секундомер", {"way": "off"}),
        ("сбрось секундомер", {"way": "reset"}),
    ]
    for text, args in stopwatch_phrases:
        prefixes = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in prefixes:
            samples.append({"query": f"{p}{text}".strip(), "tool": "stopwatch", "args": args})

    # 8. HOTKEY (WINDOW / TAB CONTROLS)
    hotkey_variations = [
        ("close this tab", ["ctrl", "w"]),
        ("close browser tab", ["ctrl", "w"]),
        ("close tab", ["ctrl", "w"]),
        ("open new tab", ["ctrl", "t"]),
        ("new tab", ["ctrl", "t"]),
        ("create tab", ["ctrl", "t"]),
        ("close window", ["alt", "f4"]),
        ("close active application", ["alt", "f4"]),
        ("switch window", ["alt", "tab"]),
        ("next window", ["alt", "tab"]),
        ("закрой вкладку", ["ctrl", "w"]),
        ("закрой эту вкладку", ["ctrl", "w"]),
        ("открой новую вкладку", ["ctrl", "t"]),
        ("новая вкладка", ["ctrl", "t"]),
        ("создай вкладку", ["ctrl", "t"]),
        ("закрой окно", ["alt", "f4"]),
        ("закрой приложение", ["alt", "f4"]),
        ("переключи окно", ["alt", "tab"]),
    ]
    for text, keys in hotkey_variations:
        prefixes = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in prefixes:
            samples.append({"query": f"{p}{text}".strip(), "tool": "hotkey", "args": {"hotkey": keys, "context": text}})

    # 9. SUBPROCESS (APPS)
    app_variations = [
        ("open files", ["xdg-open", "."], "files"),
        ("open file manager", ["xdg-open", "."], "files"),
        ("open explorer", ["xdg-open", "."], "files"),
        ("open browser", ["google-chrome"], "browser"),
        ("open chrome", ["google-chrome"], "browser"),
        ("launch terminal", ["x-terminal-emulator"], "terminal"),
        ("open terminal", ["x-terminal-emulator"], "terminal"),
        ("open code", ["code"], "code editor"),
        ("открой файлы", ["xdg-open", "."], "files"),
        ("открой проводник", ["xdg-open", "."], "files"),
        ("открой менеджер файлов", ["xdg-open", "."], "files"),
        ("открой браузер", ["google-chrome"], "browser"),
        ("запусти терминал", ["x-terminal-emulator"], "terminal"),
        ("открой консоль", ["x-terminal-emulator"], "terminal"),
        ("открой редактор кода", ["code"], "code editor"),
    ]
    for text, subp, ctx in app_variations:
        prefixes = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in prefixes:
            samples.append({"query": f"{p}{text}".strip(), "tool": "subprocess", "args": {"subprocess": subp, "context": ctx}})

    # 10. SCREENSHOT & LOCK SESSION & BATTERY
    misc_variations = [
        ("take a screenshot", "screenshot", {}),
        ("capture screen", "screenshot", {}),
        ("make a screenshot", "screenshot", {}),
        ("сделай скриншот", "screenshot", {}),
        ("сфотографируй экран", "screenshot", {}),
        ("скриншот экрана", "screenshot", {}),
        ("lock the screen", "lock_session", {}),
        ("lock session", "lock_session", {}),
        ("lock computer", "lock_session", {}),
        ("заблокируй экран", "lock_session", {}),
        ("заблокируй компьютер", "lock_session", {}),
        ("блокировка экрана", "lock_session", {}),
        ("what is my battery level", "battery_health", {}),
        ("check battery status", "battery_health", {}),
        ("how much charge is left", "battery_health", {}),
        ("уровень заряда батареи", "battery_health", {}),
        ("сколько процентов заряда", "battery_health", {}),
        ("состояние аккумулятора", "battery_health", {}),
    ]
    for text, tool, args in misc_variations:
        prefixes = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in prefixes:
            samples.append({"query": f"{p}{text}".strip(), "tool": tool, "args": args})

    # 11. PLAY SONG & FIND VIDEO
    song_queries = [
        "bohemian rhapsody", "queen radio gaga", "daft punk get lucky", "hans zimmer interstellar",
        "lo-fi hip hop chill beats", "beethoven symphony 9", "кино группа крови", "сплин мое сердце",
        "jazz cafe music", "taylor swift shake it off"
    ]
    for song in song_queries:
        samples.append({"query": f"play song {song}", "tool": "play_song", "args": {"context": song}})
        samples.append({"query": f"play music {song}", "tool": "play_song", "args": {"context": song}})
        samples.append({"query": f"включи песню {song}", "tool": "play_song", "args": {"context": song}})
        samples.append({"query": f"включи трек {song}", "tool": "play_song", "args": {"context": song}})
        samples.append({"query": f"найди видео {song}", "tool": "find_video", "args": {"context": song}})
        samples.append({"query": f"find video about {song}", "tool": "find_video", "args": {"context": song}})

    # 12. TYPING
    typing_texts = [
        "hello world", "good morning everyone", "meeting at 3 pm", "git commit -m update",
        "привет мир", "доброе утро", "совещание в три часа"
    ]
    for t_text in typing_texts:
        samples.append({"query": f"type {t_text}", "tool": "typing", "args": {"context": t_text}})
        samples.append({"query": f"type out {t_text}", "tool": "typing", "args": {"context": t_text}})
        samples.append({"query": f"напечатай {t_text}", "tool": "typing", "args": {"context": t_text}})
        samples.append({"query": f"напиши текст {t_text}", "tool": "typing", "args": {"context": t_text}})

    # 13. NEGATIVE / CHITCHAT SAMPLES (NO TOOL CALLED)
    chitchat = [
        ("who is the president of france?", "The President of the French Republic is Emmanuel Macron."),
        ("tell me a funny programming joke", "Why do programmers prefer dark mode? Because light attracts bugs!"),
        ("what is python?", "Python is a high-level, general-purpose programming language."),
        ("how does photosynthesis work?", "Photosynthesis is the process by which green plants transform light energy into chemical energy."),
        ("hello stewart how are you doing", "Hello! I am doing well, ready to assist you."),
        ("good morning stewart", "Good morning! How can I help you today?"),
        ("привет как твои дела", "Привет! Все системы работают отлично, готов к вашим командам."),
        ("кто такой альберт эйнштейн", "Альберт Эйнштейн — физик-теоретик, один из основателей современной теоретической физики."),
        ("расскажи шутку", "Заходит программист в лифт, а ему говорят: 'Вам какой этаж?' — 'Мне единицу, пожалуйста'."),
        ("какая столица японии", "Столица Японии — Токио."),
        ("what is 25 times 4", "25 multiplied by 4 equals 100."),
        ("спасибо за помощь", "Пожалуйста! Рад был помочь.")
    ]
    for q, ans in chitchat:
        samples.append({"query": q, "tool": None, "args": None, "response": ans})

    return samples


def format_qwen_tool_prompt(tools: List[Dict[str, Any]]) -> str:
    """Formats system prompt with tool documentation in standard Qwen format."""
    tool_descs = []
    for t in tools:
        schema_json = json.dumps(t, indent=2, ensure_ascii=False)
        tool_descs.append(f"## {t['name']}\n\n```json\n{schema_json}\n```")

    tools_block = "\n\n".join(tool_descs)
    return (
        "You are Stewart, an intelligent AI voice assistant running on Linux. "
        "You have access to the following tools to execute user commands:\n\n"
        f"# Tools\n\n{tools_block}\n\n"
        "When the user's request corresponds to an available tool, call the single best tool using:\n"
        "<tool_call>\n"
        "{\"name\": \"tool_name\", \"arguments\": {\"param\": \"value\"}}\n"
        "</tool_call>\n\n"
        "If the user is asking a general question, greeting, or chatting and no tool applies, answer directly without tool calls."
    )


def build_qwen_conversations(samples: List[Dict[str, Any]], system_prompt: str) -> List[Dict[str, Any]]:
    dataset = []

    for item in samples:
        query = item["query"]
        tool_name = item.get("tool")
        tool_args = item.get("args")

        if tool_name is not None and tool_args is not None:
            tool_call_content = f"<tool_call>\n{json.dumps({'name': tool_name, 'arguments': tool_args}, ensure_ascii=False)}\n</tool_call>"
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
                {"role": "assistant", "content": tool_call_content}
            ]
        else:
            resp = item.get("response", "I am here to help.")
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
                {"role": "assistant", "content": resp}
            ]

        dataset.append({"messages": messages})

    return dataset


def main():
    output_dir = Path(__file__).resolve().parent.parent / "data/dataset"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Generating base synthetic tool calling samples...")
    raw_samples = generate_samples()
    print(f"Generated {len(raw_samples)} unique sample patterns.")

    # Expand and balance to reach thousands of samples with speech noise / variations
    expanded = []
    fillers_en = ["", "uh ", "um ", "well ", "now ", "so "]
    fillers_ru = ["", "эм ", "ну ", "так ", "слушай "]

    for s in raw_samples:
        expanded.append(s)
        q = s["query"]
        is_ru = any(ord(c) > 127 for c in q)
        fillers = fillers_ru if is_ru else fillers_en
        for filler in fillers[1:3]:
            expanded.append({
                "query": f"{filler}{q}",
                "tool": s["tool"],
                "args": s["args"],
                "response": s.get("response")
            })

    random.seed(42)
    random.shuffle(expanded)
    print(f"Total dataset size after augmentation: {len(expanded)} examples.")

    system_prompt = format_qwen_tool_prompt(STEWART_TOOLS)
    conversations = build_qwen_conversations(expanded, system_prompt)

    # Train / Val split (90% / 10%)
    split_idx = int(len(conversations) * 0.9)
    train_data = conversations[:split_idx]
    val_data = conversations[split_idx:]

    train_file = output_dir / "train.jsonl"
    val_file = output_dir / "val.jsonl"
    tools_file = output_dir / "stewart_tools.json"

    with open(train_file, "w", encoding="utf-8") as f:
        for ex in train_data:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    with open(val_file, "w", encoding="utf-8") as f:
        for ex in val_data:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    with open(tools_file, "w", encoding="utf-8") as f:
        json.dump(STEWART_TOOLS, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(train_data)} train samples to {train_file}")
    print(f"Wrote {len(val_data)} val samples to {val_file}")
    print(f"Saved tools schema to {tools_file}")


if __name__ == "__main__":
    main()
