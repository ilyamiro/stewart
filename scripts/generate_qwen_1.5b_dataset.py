#!/usr/bin/env python3
"""
Enhanced Dataset Generator for Qwen2.5-1.5B (Tool Calling & Butler Voice Persona).
Expands tool coverage to include MCP tools (Studieplus, Gmail) and Dynamic Tools,
incorporates rich bilingual (EN/RU) phrasings, speech variations, and negative chitchat,
and formats system prompts with compact candidate tool schemas to optimize sequence length
and VRAM footprint (<200 tokens) for high-speed training on RTX 3050 (3.2-3.3 GB VRAM).
"""

import json
import random
from pathlib import Path
from typing import List, Dict, Any, Optional

ALL_TOOLS = [
    # Built-in Core Tools
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
                "context": {"type": "string", "description": "Optional media details or search query"}
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
                "context": {"type": "string", "description": "Amount, percentage or specific volume level (e.g. '50%', '10', 'maximum')"}
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
                "context": {"type": "string", "description": "Percentage or level (e.g. '80%', 'max', 'minimum')"}
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
                "context": {"type": "string", "description": "Optional format request (e.g. 'date', 'time', 'exact')"}
            }
        }
    },
    {
        "name": "say_weather",
        "description": "Fetch and announce the current weather forecast.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "Optional city name or location"}
            }
        }
    },
    {
        "name": "timer",
        "description": "Set, start or cancel a countdown timer.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "Timer duration (e.g. '5 minutes', '30 seconds', '1 hour', '10 мин')"},
                "action": {"type": "string", "enum": ["set", "cancel", "status"], "default": "set"}
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
                "way": {"type": "string", "enum": ["on", "off", "reset", "lap"], "description": "Stopwatch operation"}
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
                "hotkey": {"type": "array", "items": {"type": "string"}, "description": "Key combination list, e.g. ['ctrl', 'w'] to close tab, ['ctrl', 't'] for new tab, ['alt', 'f4'] to close window"},
                "context": {"type": "string", "description": "Target description"}
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
                "subprocess": {"type": "array", "items": {"type": "string"}, "description": "Application command to execute, e.g. ['xdg-open', '.'] or ['nautilus'] or ['google-chrome']"},
                "context": {"type": "string", "description": "File or folder name or app name"}
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
                "context": {"type": "string", "description": "Optional area specification ('full', 'window', 'selection')"}
            }
        }
    },
    {
        "name": "lock_session",
        "description": "Lock the user session or screen immediately.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "battery_health",
        "description": "Report current battery state, percentage, and health status.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "play_song",
        "description": "Search and play a specific song, artist, or music track on YouTube/YouTube Music.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "Song title or artist query"}
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
                "context": {"type": "string", "description": "Search phrase or topic for the video"}
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
                "context": {"type": "string", "description": "Text to type out"}
            },
            "required": ["context"]
        }
    },

    # Dynamic Tools
    {
        "name": "change_file_name",
        "description": "Rename or move a file or folder on the local Linux filesystem.",
        "parameters": {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Source path"},
                "dst": {"type": "string", "description": "Destination path"}
            },
            "required": ["src", "dst"]
        }
    },

    # MCP Studieplus Tools
    {
        "name": "studieplus_get_schedule",
        "description": "Fetch school timetable and class schedule for a specific day or week from Studieplus.",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {"type": "string", "description": "Target day (e.g. 'today', 'tomorrow', 'monday', 'next week')"}
            }
        }
    },
    {
        "name": "studieplus_get_assignments",
        "description": "Get homework, deadlines, and pending assignments from Studieplus.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "all", "upcoming"], "description": "Filter assignments by status"},
                "subject": {"type": "string", "description": "Optional school subject name (e.g. 'Math', 'Physics', 'History')"}
            }
        }
    },
    {
        "name": "studieplus_get_conversations",
        "description": "Check recent school messages, announcements, or communications from teachers.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional search keyword or teacher name"}
            }
        }
    },
    {
        "name": "studieplus_check_session",
        "description": "Check if Studieplus school session and authentication are active.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "study_get_ib_resources",
        "description": "Retrieve IB Diploma study materials, past exam papers, question banks, or syllabus guidelines.",
        "parameters": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "IB subject (e.g. 'Mathematics HL', 'Physics HL', 'Economics SL')"},
                "resource_type": {"type": "string", "enum": ["past_papers", "study_guide", "question_bank", "syllabus"], "description": "Type of resource requested"}
            },
            "required": ["subject"]
        }
    },
    {
        "name": "study_prepare_test",
        "description": "Generate revision quiz questions, flashcards, or practice test problems for school study.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Subject or specific topic to practice (e.g. 'Calculus Derivatives', 'Wave Optics')"},
                "difficulty": {"type": "string", "enum": ["standard", "higher", "easy", "hard"], "description": "Level of difficulty"}
            },
            "required": ["topic"]
        }
    },

    # MCP Gmail Tools
    {
        "name": "gmail_check_status",
        "description": "Check Gmail connection and report count of unread emails or new messages.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "gmail_search_emails",
        "description": "Search user Gmail inbox for specific emails by sender, subject, query keyword, or date.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query or sender name (e.g. 'from:teacher', 'invoice', 'Google')"},
                "max_results": {"type": "integer", "description": "Maximum number of email results to return"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "gmail_send_email",
        "description": "Compose and send an email via Gmail.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Subject line of the email"},
                "body": {"type": "string", "description": "Body message text"}
            },
            "required": ["to", "subject", "body"]
        }
    }
]

EN_PREFIXES = [
    "", "please ", "stewart ", "hey stewart ", "stewart please ", "could you ", "can you please ",
    "would you mind to ", "go ahead and ", "just ", "quick question ", "hey "
]
RU_PREFIXES = [
    "", "пожалуйста ", "стюарт ", "стюарт пожалуйста ", "эй стюарт ", "можешь ", "сделай ",
    "будь добр ", "пожалуйста сделай ", "давай ", "просто "
]


def format_compact_schema(tool: Dict[str, Any]) -> str:
    """Produces a dense single-line representation of a tool schema for compact prompts."""
    name = tool["name"]
    params = tool.get("parameters", {}).get("properties", {})
    param_strs = []
    for pname, pinfo in params.items():
        ptype = pinfo.get("type", "any")
        if "enum" in pinfo:
            ptype = "|".join(f'"{e}"' for e in pinfo["enum"])
        param_strs.append(f"{pname}: {ptype}")
    params_repr = ", ".join(param_strs)
    desc = tool.get("description", "")
    return f"{name}({params_repr}) - {desc}"


def generate_all_samples() -> List[Dict[str, Any]]:
    samples = []

    # 1. MEDIA CONTROL
    media = [
        ("pause the music", "media_control", {"control": "play-pause"}),
        ("pause playback", "media_control", {"control": "play-pause"}),
        ("pause video", "media_control", {"control": "play-pause"}),
        ("unpause the song", "media_control", {"control": "play-pause"}),
        ("resume playback", "media_control", {"control": "play-pause"}),
        ("resume music", "media_control", {"control": "play-pause"}),
        ("stop the music", "media_control", {"control": "play-pause"}),
        ("halt audio", "media_control", {"control": "play-pause"}),
        ("skip this track", "media_control", {"control": "next"}),
        ("next song", "media_control", {"control": "next"}),
        ("next track please", "media_control", {"control": "next"}),
        ("previous song", "media_control", {"control": "previous"}),
        ("previous track", "media_control", {"control": "previous"}),
        ("go back to last song", "media_control", {"control": "previous"}),
        ("mute the sound", "media_control", {"control": "mute"}),
        ("unmute audio", "media_control", {"control": "unmute"}),
        ("поставь на паузу", "media_control", {"control": "play-pause"}),
        ("пауза музыки", "media_control", {"control": "play-pause"}),
        ("останови воспроизведение", "media_control", {"control": "play-pause"}),
        ("возобнови музыку", "media_control", {"control": "play-pause"}),
        ("продолжи воспроизведение", "media_control", {"control": "play-pause"}),
        ("сними с паузы", "media_control", {"control": "play-pause"}),
        ("следующий трек", "media_control", {"control": "next"}),
        ("следующая песня", "media_control", {"control": "next"}),
        ("переключи на следующий", "media_control", {"control": "next"}),
        ("скипни песню", "media_control", {"control": "next"}),
        ("предыдущий трек", "media_control", {"control": "previous"}),
        ("предыдущая песня", "media_control", {"control": "previous"}),
        ("заглуши звук", "media_control", {"control": "mute"}),
        ("включи звук обратно", "media_control", {"control": "unmute"}),
    ]
    for text, tool, args in media:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": tool, "args": args})

    # 2. VOLUME
    vol_steps = ["5", "10", "15", "20", "25", "30%", "40%", "50%", "60%", "70%", "80%", "90%", "100%", "max"]
    for s in vol_steps:
        samples.append({"query": f"set volume to {s}", "tool": "volume", "args": {"command": "set", "context": s}})
        samples.append({"query": f"volume {s}", "tool": "volume", "args": {"command": "set", "context": s}})
        samples.append({"query": f"установи громкость на {s}", "tool": "volume", "args": {"command": "set", "context": s}})
        samples.append({"query": f"сделай звук {s}", "tool": "volume", "args": {"command": "set", "context": s}})

    vols = [
        ("make it louder", "volume", {"command": "up", "context": "10"}),
        ("turn up the sound", "volume", {"command": "up", "context": "10"}),
        ("volume up please", "volume", {"command": "up", "context": "10"}),
        ("boost audio", "volume", {"command": "up", "context": "10"}),
        ("turn the sound down", "volume", {"command": "down", "context": "10"}),
        ("volume down", "volume", {"command": "down", "context": "10"}),
        ("make it quieter", "volume", {"command": "down", "context": "10"}),
        ("lower the sound", "volume", {"command": "down", "context": "10"}),
        ("сделай погромче", "volume", {"command": "up", "context": "10"}),
        ("прибавь звук", "volume", {"command": "up", "context": "10"}),
        ("увеличь громкость", "volume", {"command": "up", "context": "10"}),
        ("сделай тише", "volume", {"command": "down", "context": "10"}),
        ("убавь громкость", "volume", {"command": "down", "context": "10"}),
        ("потише звук", "volume", {"command": "down", "context": "10"}),
        ("mute master sound", "volume", {"command": "mute", "context": ""}),
        ("выключи звук полностью", "volume", {"command": "mute", "context": ""}),
    ]
    for text, tool, args in vols:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": tool, "args": args})

    # 3. BRIGHTNESS
    bright = [
        ("screen brightness up", "brightness", {"command": "up", "context": "10"}),
        ("increase display brightness", "brightness", {"command": "up", "context": "10"}),
        ("make screen brighter", "brightness", {"command": "up", "context": "10"}),
        ("dim the screen", "brightness", {"command": "down", "context": "10"}),
        ("lower screen brightness", "brightness", {"command": "down", "context": "10"}),
        ("make screen darker", "brightness", {"command": "down", "context": "10"}),
        ("прибавь яркость экрана", "brightness", {"command": "up", "context": "10"}),
        ("сделай экран поярче", "brightness", {"command": "up", "context": "10"}),
        ("увеличь яркость дисплея", "brightness", {"command": "up", "context": "10"}),
        ("убавь яркость", "brightness", {"command": "down", "context": "10"}),
        ("сделай потемнее экран", "brightness", {"command": "down", "context": "10"}),
    ]
    for text, tool, args in bright:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": tool, "args": args})

    for bval in ["30%", "50%", "70%", "80%", "100%", "maximum"]:
        samples.append({"query": f"set brightness to {bval}", "tool": "brightness", "args": {"command": "set", "context": bval}})
        samples.append({"query": f"поставь яркость на {bval}", "tool": "brightness", "args": {"command": "set", "context": bval}})

    # 4. TELL TIME & WEATHER
    times = [
        "what time is it", "tell me the time", "current time please", "what hour is it",
        "сколько сейчас времени", "который час", "подскажи время", "назови точное время"
    ]
    for t in times:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in t) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{t}".strip(), "tool": "tell_time", "args": {}})

    weathers = [
        ("what is the weather like", ""), ("how is the weather outside", ""),
        ("weather in Berlin", "Berlin"), ("weather in London", "London"), ("weather in Paris", "Paris"),
        ("какая сейчас погода", ""), ("какая погода в Москве", "Москва"), ("погода в Санкт-Петербурге", "Санкт-Петербург")
    ]
    for wtext, loc in weathers:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in wtext) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{wtext}".strip(), "tool": "say_weather", "args": {"context": loc} if loc else {}})

    # 5. TIMER & STOPWATCH
    tdurs = [
        ("5 minutes", "5 minutes"), ("10 minutes", "10 minutes"), ("15 minutes", "15 minutes"),
        ("1 hour", "1 hour"), ("30 seconds", "30 seconds"),
        ("5 минут", "5 минут"), ("10 минут", "10 минут"), ("15 минут", "15 минут"), ("полчаса", "30 минут")
    ]
    for dtext, dnorm in tdurs:
        samples.append({"query": f"set a timer for {dtext}", "tool": "timer", "args": {"context": dnorm, "action": "set"}})
        samples.append({"query": f"timer {dtext}", "tool": "timer", "args": {"context": dnorm, "action": "set"}})
        samples.append({"query": f"поставь таймер на {dtext}", "tool": "timer", "args": {"context": dnorm, "action": "set"}})
        samples.append({"query": f"таймер {dtext}", "tool": "timer", "args": {"context": dnorm, "action": "set"}})

    sws = [
        ("start stopwatch", {"way": "on"}), ("stop stopwatch", {"way": "off"}), ("reset stopwatch", {"way": "reset"}),
        ("запусти секундомер", {"way": "on"}), ("останови секундомер", {"way": "off"}), ("сбрось секундомер", {"way": "reset"})
    ]
    for text, args in sws:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": "stopwatch", "args": args})

    # 6. HOTKEY & APPS & SYSTEM
    hk_apps = [
        ("close this tab", "hotkey", {"hotkey": ["ctrl", "w"], "context": "close tab"}),
        ("open new tab", "hotkey", {"hotkey": ["ctrl", "t"], "context": "new tab"}),
        ("close this window", "hotkey", {"hotkey": ["alt", "f4"], "context": "close window"}),
        ("закрой вкладку", "hotkey", {"hotkey": ["ctrl", "w"], "context": "close tab"}),
        ("открой новую вкладку", "hotkey", {"hotkey": ["ctrl", "t"], "context": "new tab"}),
        ("закрой окно", "hotkey", {"hotkey": ["alt", "f4"], "context": "close window"}),
        ("open file manager", "subprocess", {"subprocess": ["xdg-open", "."], "context": "files"}),
        ("open browser", "subprocess", {"subprocess": ["google-chrome"], "context": "browser"}),
        ("open terminal", "subprocess", {"subprocess": ["x-terminal-emulator"], "context": "terminal"}),
        ("launch code editor", "subprocess", {"subprocess": ["code"], "context": "code editor"}),
        ("открой проводник", "subprocess", {"subprocess": ["xdg-open", "."], "context": "files"}),
        ("открой терминал", "subprocess", {"subprocess": ["x-terminal-emulator"], "context": "terminal"}),
        ("запусти браузер", "subprocess", {"subprocess": ["google-chrome"], "context": "browser"}),
        ("take a screenshot", "screenshot", {}),
        ("capture the screen", "screenshot", {}),
        ("сделай скриншот", "screenshot", {}),
        ("lock the screen", "lock_session", {}),
        ("lock my computer", "lock_session", {}),
        ("заблокируй экран", "lock_session", {}),
        ("check battery status", "battery_health", {}),
        ("what is my battery level", "battery_health", {}),
        ("уровень заряда батареи", "battery_health", {})
    ]
    for text, tool, args in hk_apps:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": tool, "args": args})

    # 7. SONGS & VIDEOS & TYPING
    songs = [
        ("play song bohemian rhapsody", "play_song", {"context": "bohemian rhapsody"}),
        ("play music daft punk", "play_song", {"context": "daft punk"}),
        ("включи песню группа крови", "play_song", {"context": "группа крови"}),
        ("find video about quantum computing", "find_video", {"context": "quantum computing"}),
        ("найди видео про черные дыры", "find_video", {"context": "черные дыры"}),
        ("type hello world", "typing", {"context": "hello world"}),
        ("напечатай добрый вечер", "typing", {"context": "добрый вечер"})
    ]
    for text, tool, args in songs:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": tool, "args": args})

    # =========================================================================
    # 8. MCP TOOLS & DYNAMIC TOOLS (NEW & ENHANCED)
    # =========================================================================

    # Dynamic Tool: change_file_name
    rename_samples = [
        ("rename notes.txt to notes_backup.txt", {"src": "notes.txt", "dst": "notes_backup.txt"}),
        ("change file name report.pdf to final_report.pdf", {"src": "report.pdf", "dst": "final_report.pdf"}),
        ("move document.docx to archive.docx", {"src": "document.docx", "dst": "archive.docx"}),
        ("переименуй файл data.json в data_old.json", {"src": "data.json", "dst": "data_old.json"}),
        ("переименуй фото img1.png в avatar.png", {"src": "img1.png", "dst": "avatar.png"}),
        ("смени имя файла draft.txt на publication.txt", {"src": "draft.txt", "dst": "publication.txt"})
    ]
    for text, args in rename_samples:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": "change_file_name", "args": args})

    # MCP Studieplus: Schedule
    schedule_samples = [
        ("what is my school schedule today", {"day": "today"}),
        ("check today's timetable", {"day": "today"}),
        ("what classes do I have today", {"day": "today"}),
        ("what is on my schedule for tomorrow", {"day": "tomorrow"}),
        ("check timetable for tomorrow", {"day": "tomorrow"}),
        ("show my monday class schedule", {"day": "monday"}),
        ("what is my schedule for next week", {"day": "next week"}),
        ("какое у меня расписание на сегодня", {"day": "today"}),
        ("какие уроки сегодня в школе", {"day": "today"}),
        ("что у меня по расписанию завтра", {"day": "tomorrow"}),
        ("покажи расписание на понедельник", {"day": "monday"}),
        ("какое расписание на следующую неделю", {"day": "next week"})
    ]
    for text, args in schedule_samples:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": "studieplus_get_schedule", "args": args})

    # MCP Studieplus: Assignments & Homework
    assign_samples = [
        ("what homework do I have due", {"status": "pending"}),
        ("check pending assignments in Studieplus", {"status": "pending"}),
        ("do I have any upcoming homework", {"status": "upcoming"}),
        ("show all assignments for math", {"status": "all", "subject": "Math"}),
        ("check physics homework deadlines", {"status": "pending", "subject": "Physics"}),
        ("какая домашняя работа задана", {"status": "pending"}),
        ("какие задания висят в studieplus", {"status": "pending"}),
        ("проверь домашку по математике", {"status": "all", "subject": "Math"}),
        ("есть ли дедлайны по физике", {"status": "pending", "subject": "Physics"}),
        ("покажи все невыполненные задания", {"status": "pending"})
    ]
    for text, args in assign_samples:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": "studieplus_get_assignments", "args": args})

    # MCP Studieplus: School Conversations & Messages
    conv_samples = [
        ("check my school messages in Studieplus", {}),
        ("did my teacher send any announcements", {}),
        ("search messages from Mr. Anderson", {"query": "Mr. Anderson"}),
        ("any recent messages from school", {}),
        ("проверь школьные сообщения в studieplus", {}),
        ("писали ли преподаватели объявления", {}),
        ("найди сообщения от учителя математики", {"query": "математика"}),
        ("есть ли новые сообщения из школы", {})
    ]
    for text, args in conv_samples:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": "studieplus_get_conversations", "args": args})

    # MCP Studieplus: Session check
    sess_samples = [
        ("check if Studieplus session is active", {}),
        ("am I logged into Studieplus", {}),
        ("проверь сессию studieplus", {}),
        ("активен ли вход в школьный портал", {})
    ]
    for text, args in sess_samples:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": "studieplus_check_session", "args": args})

    # MCP Study IB Resources & Test Prep
    study_samples = [
        ("get IB past papers for Mathematics HL", "study_get_ib_resources", {"subject": "Mathematics HL", "resource_type": "past_papers"}),
        ("fetch physics study guide for IB", "study_get_ib_resources", {"subject": "Physics HL", "resource_type": "study_guide"}),
        ("get question bank for chemistry SL", "study_get_ib_resources", {"subject": "Chemistry SL", "resource_type": "question_bank"}),
        ("подбери экзаменационные билеты IB по математике", "study_get_ib_resources", {"subject": "Mathematics HL", "resource_type": "past_papers"}),
        ("найди материалы подготовки IB по физике", "study_get_ib_resources", {"subject": "Physics HL", "resource_type": "study_guide"}),
        ("prepare a practice test on Calculus derivatives", "study_prepare_test", {"topic": "Calculus derivatives", "difficulty": "higher"}),
        ("quiz me on wave optics", "study_prepare_test", {"topic": "wave optics", "difficulty": "standard"}),
        ("создай проверочный тест по кинематике", "study_prepare_test", {"topic": "кинематика", "difficulty": "standard"}),
        ("подготовь практические вопросы по интегралам", "study_prepare_test", {"topic": "интегралы", "difficulty": "hard"})
    ]
    for text, tool, args in study_samples:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": tool, "args": args})

    # MCP Gmail: Check Status & Search & Send
    gmail_samples = [
        ("check my email status", "gmail_check_status", {}),
        ("do I have any unread emails", "gmail_check_status", {}),
        ("check gmail for new messages", "gmail_check_status", {}),
        ("проверь почту gmail", "gmail_check_status", {}),
        ("есть ли новые письма на почте", "gmail_check_status", {}),
        ("сколько непрочитанных сообщений в gmail", "gmail_check_status", {}),
        ("search emails from teacher", "gmail_search_emails", {"query": "from:teacher", "max_results": 5}),
        ("find emails about project deadline", "gmail_search_emails", {"query": "project deadline", "max_results": 5}),
        ("search inbox for GitHub notifications", "gmail_search_emails", {"query": "GitHub", "max_results": 5}),
        ("найди письма от университета", "gmail_search_emails", {"query": "университет", "max_results": 5}),
        ("поищи в почте квитанцию об оплате", "gmail_search_emails", {"query": "квитанция", "max_results": 5}),
        ("send email to teacher@school.org about homework", "gmail_send_email", {"to": "teacher@school.org", "subject": "Homework submission", "body": "Dear teacher, here is my homework."}),
        ("отправь письмо на test@example.com с темой Отчет", "gmail_send_email", {"to": "test@example.com", "subject": "Отчет", "body": "Здравствуйте, высылаю отчет."})
    ]
    for text, tool, args in gmail_samples:
        pref = RU_PREFIXES if any(ord(c) > 127 for c in text) else EN_PREFIXES
        for p in pref[:6]:
            samples.append({"query": f"{p}{text}".strip(), "tool": tool, "args": args})

    # 9. NEGATIVE / GENERAL CHITCHAT (NO TOOL DISPATCHED)
    chitchat = [
        ("who is the current prime minister of the UK?", "The Prime Minister of the United Kingdom is Keir Starmer, sir."),
        ("tell me an elegant programming joke", "Why do programmers prefer dark mode? Because light attracts bugs, sir."),
        ("what is an operating system kernel?", "The kernel is the core program that manages system resources and hardware communication, sir."),
        ("how does quantum entanglement work in physics?", "Quantum entanglement describes particles whose states remain interconnected regardless of distance, sir."),
        ("good morning Stewart, how are you today?", "Good morning, sir. All subsystems are optimal and ready for your commands."),
        ("thank you very much Stewart", "It is my absolute pleasure to assist, sir."),
        ("доброе утро Стюарт как твои дела", "Доброе утро, сэр. Все системы функционируют безупречно."),
        ("кто такой иссак ньютон", "Исаак Ньютон — великий английский физик и математик, открывший закон всемирного тяготения, сэр."),
        ("расскажи короткую шутку", "Теория — это когда всё известно, но ничего не работает. Практика — когда всё работает, но никто не знает почему."),
        ("какое расстояние от Земли до Луны", "Среднее расстояние до Луны составляет около 384 тысяч километров, сэр."),
        ("спасибо за помощь Стюарт", "Всегда к вашим услугам, сэр.")
    ]
    for q, ans in chitchat:
        samples.append({"query": q, "tool": None, "args": None, "response": ans})

    return samples


def build_compact_tool_prompt(target_tool_name: Optional[str], all_tools: List[Dict[str, Any]]) -> str:
    """
    Builds a compact prompt containing candidate tool schemas.
    To ensure prompt length remains <= 170 tokens while maintaining high accuracy:
    If target_tool_name is provided: includes target tool + 2 random distractor tools.
    If no tool (chitchat): includes 3 random candidate tools.
    """
    tools_by_name = {t["name"]: t for t in all_tools}
    selected_tools = []

    if target_tool_name and target_tool_name in tools_by_name:
        selected_tools.append(tools_by_name[target_tool_name])

    other_tools = [t for t in all_tools if t["name"] != target_tool_name]
    distractors = random.sample(other_tools, min(2, len(other_tools)))
    selected_tools.extend(distractors)
    random.shuffle(selected_tools)

    lines = [format_compact_schema(t) for t in selected_tools]
    tools_str = "\n".join(f"- {l}" for l in lines)

    return (
        "You are Stewart, an intelligent Linux AI voice assistant.\n"
        f"Available tools:\n{tools_str}\n"
        "Call single tool using: <tool_call>{\"name\": \"...\", \"arguments\": {...}}</tool_call>.\n"
        "If no tool applies, answer directly."
    )


def generate_persona_samples() -> List[Dict[str, Any]]:
    """Generates comprehensive bilingual refined British butler voice persona examples."""
    sys_en = (
        "You are Stewart, an intelligent, refined AI butler running on Linux. "
        "You speak concisely (1-2 sentences) in a polite, respectful tone, addressing the user as Sir or Illia. "
        "You confirm actions smoothly and provide witty, helpful answers."
    )
    sys_ru = (
        "Вы — Стюарт, умный и вежливый голосовой дворецкий для Linux. "
        "Вы говорите лаконично (1-2 предложения), уважительно, называя пользователя сэр или Илья. "
        "Вы изящно подтверждаете действия и даете остроумные, полезные ответы."
    )

    examples = []

    # First load existing high quality persona dataset
    existing_file = Path(__file__).resolve().parent.parent / "data/dataset/persona_train.jsonl"
    if existing_file.exists():
        with open(existing_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    # Filter out any unusually long dialogue
                    total_chars = sum(len(m.get("content", "")) for m in data.get("messages", []))
                    if total_chars < 500:
                        examples.append(data)
                except Exception:
                    pass

    # MCP Studieplus Schedule
    sched_cases = [
        ("en", "What is my schedule for today Stewart?", "studieplus_get_schedule", {"day": "today", "classes": ["Mathematics HL", "Physics HL", "English Literature"]}, "Here is your timetable for today, sir. You have Mathematics followed by Physics and English."),
        ("en", "Do I have school tomorrow?", "studieplus_get_schedule", {"day": "tomorrow", "classes": ["Chemistry", "History"]}, "Tomorrow you have Chemistry followed by History, Illia. A well-balanced day ahead."),
        ("ru", "Стюарт, какое у меня расписание на сегодня?", "studieplus_get_schedule", {"day": "today", "classes": ["Математика", "Физика"]}, "На сегодня у вас математика и физика, сэр. Желаю продуктивного дня."),
        ("ru", "Что по урокам на завтра?", "studieplus_get_schedule", {"day": "tomorrow", "classes": ["Химия", "История"]}, "Завтра в вашем расписании химия и история, Илья.")
    ]
    # MCP Studieplus Assignments
    hw_cases = [
        ("en", "Check my pending assignments Stewart.", "studieplus_get_assignments", {"count": 2, "items": ["Math problem set", "Physics lab"]}, "You have two assignments due, sir: the Mathematics problem set and your Physics lab report."),
        ("en", "Any homework for tonight?", "studieplus_get_assignments", {"count": 0}, "No pending assignments detected for tonight, sir. An excellent opportunity to relax."),
        ("ru", "Какая домашка задана?", "studieplus_get_assignments", {"count": 2, "items": ["Математика", "Физика"]}, "У вас два активных задания, сэр: упражнения по математике и лабораторная по физике."),
        ("ru", "Есть ли долги по учебе?", "studieplus_get_assignments", {"count": 0}, "Никаких задолженностей нет, Илья. Все сдано вовремя.")
    ]
    # MCP Gmail
    mail_cases = [
        ("en", "Do I have any unread emails?", "gmail_check_status", {"unread": 3}, "You have three unread messages in your inbox, sir, including an update from school."),
        ("en", "Check my Gmail please.", "gmail_check_status", {"unread": 0}, "Your inbox is completely clear, sir. Not a single unread message."),
        ("ru", "Проверь новые письма на почте.", "gmail_check_status", {"unread": 2}, "В вашем ящике два новых письма, сэр. Одно из них от преподавателя."),
        ("ru", "Есть непрочитанные сообщения в Gmail?", "gmail_check_status", {"unread": 0}, "Входящих нет, сэр. Почтовый ящик в полном порядке.")
    ]
    # MCP Study Resources & Prep
    study_cases = [
        ("en", "Stewart, fetch IB past papers for Mathematics HL.", "study_get_ib_resources", {"status": "success", "subject": "Mathematics HL"}, "I have retrieved the IB Mathematics HL past papers, sir. They are ready for your revision."),
        ("en", "Prepare a quiz on Calculus derivatives.", "study_prepare_test", {"topic": "Calculus", "questions": 5}, "Practice quiz prepared, Illia. Five calculus problems await your expertise."),
        ("ru", "Подготовь тест по физике.", "study_prepare_test", {"topic": "Физика", "questions": 5}, "Проверочный тест по физике готов, сэр. Можем приступать."),
        ("ru", "Найди материалы IB по математике.", "study_get_ib_resources", {"status": "success", "subject": "Математика"}, "Материалы IB успешно получены и подготовлены к работе, Илья.")
    ]
    # Dynamic tool
    rename_cases = [
        ("en", "Rename notes.txt to notes_backup.txt please.", "change_file_name", {"status": "success", "src": "notes.txt", "dst": "notes_backup.txt"}, "File successfully renamed to notes_backup.txt, sir."),
        ("ru", "Стюарт, переименуй отчет в final_report.pdf.", "change_file_name", {"status": "success"}, "Файл переименован в final_report.pdf, сэр.")
    ]

    base_cases = sched_cases + hw_cases + mail_cases + study_cases + rename_cases
    for lang, q, tool, res, ans in base_cases:
        sys_p = sys_ru if lang == "ru" else sys_en
        msgs = [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": q},
            {"role": "tool", "name": tool, "content": json.dumps(res, ensure_ascii=False)},
            {"role": "assistant", "content": ans}
        ]
        examples.append({"messages": msgs})

    # Augment newly added cases with polite variations
    polite_fillers_en = ["", "Stewart, ", "Please, ", "Could you ", "Hey Stewart, "]
    polite_fillers_ru = ["", "Стюарт, ", "Пожалуйста, ", "Будь добр, ", "Эй Стюарт, "]

    augmented = []
    for ex in examples:
        augmented.append(ex)
        m = ex["messages"]
        if len(m) >= 4 and m[2].get("role") == "tool":
            is_ru = any(ord(c) > 127 for c in m[1]["content"])
            fillers = polite_fillers_ru if is_ru else polite_fillers_en
            for f in fillers[1:4]:
                new_msgs = [
                    m[0],
                    {"role": "user", "content": f"{f}{m[1]['content']}"},
                    m[2],
                    m[3]
                ]
                augmented.append({"messages": new_msgs})

    random.seed(42)
    random.shuffle(augmented)
    return augmented
    # Core system tools (Volume, Brightness, Media, Weather, Timer)
    core_cases = [
        ("en", "Lower the volume a bit Stewart.", "volume", {"status": "success", "volume": 35}, "Volume reduced to thirty-five percent, sir."),
        ("en", "Make it louder.", "volume", {"status": "success", "volume": 65}, "Audio level raised to sixty-five percent, sir."),
        ("en", "Make the screen a bit brighter.", "brightness", {"status": "success", "brightness": 80}, "Display brightness established at eighty percent, sir."),
        ("en", "Pause the music.", "media_control", {"status": "success", "control": "play-pause"}, "Playback paused, sir."),
        ("en", "Next track please Stewart.", "media_control", {"status": "success", "control": "next"}, "Advancing to the next track, Illia."),
        ("en", "Set a timer for 10 minutes for my tea.", "timer", {"status": "set", "duration": "10 minutes"}, "Ten minute timer running, sir. I shall notify you when your tea is ready."),
        ("en", "How is the weather in Berlin today?", "say_weather", {"city": "Berlin", "temp": 17, "cond": "cloudy"}, "It is currently 17 degrees and overcast in Berlin, sir. Rain remains improbable."),
        ("ru", "Сделай потише звук.", "volume", {"status": "success", "volume": 30}, "Громкость снижена до тридцати процентов, сэр."),
        ("ru", "Сделай экран поярче.", "brightness", {"status": "success", "brightness": 85}, "Яркость увеличена до восьмидесяти пяти процентов, сэр."),
        ("ru", "Поставь музыку на паузу.", "media_control", {"status": "success"}, "Воспроизведение приостановлено, сэр."),
        ("ru", "Поставь таймер на 15 минут.", "timer", {"status": "set", "duration": "15 минут"}, "Таймер на пятнадцать минут запущен, сэр."),
        ("ru", "Какая погода в Москве?", "say_weather", {"city": "Москва", "temp": 5, "cond": "ясно"}, "В Москве сейчас пять градусов тепла и ясно, сэр.")
    ]

    base_cases = sched_cases + hw_cases + mail_cases + study_cases + rename_cases + core_cases

    for lang, q, tool, res, ans in base_cases:
        sys_p = sys_ru if lang == "ru" else sys_en
        msgs = [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": q},
            {"role": "tool", "name": tool, "content": json.dumps(res, ensure_ascii=False)},
            {"role": "assistant", "content": ans}
        ]
        examples.append({"messages": msgs})

    # Augment with phrasing variations & polite butler variations
    augmented = []
    polite_fillers_en = ["", "Stewart, ", "Please, ", "Could you ", "Hey Stewart, "]
    polite_fillers_ru = ["", "Стюарт, ", "Пожалуйста, ", "Будь добр, ", "Эй Стюарт, "]

    for ex in examples:
        augmented.append(ex)
        m = ex["messages"]
        is_ru = any(ord(c) > 127 for c in m[1]["content"])
        fillers = polite_fillers_ru if is_ru else polite_fillers_en
        for f in fillers[1:4]:
            new_msgs = [
                m[0],
                {"role": "user", "content": f"{f}{m[1]['content']}"},
                m[2],
                m[3]
            ]
            augmented.append({"messages": new_msgs})

    # Add conversational turns without tools
    dialogue_pairs = [
        ("en", "Good morning Stewart.", "Good morning, sir. Systems are online and ready for your instruction."),
        ("en", "How are you doing today?", "Functioning at peak efficiency, sir. Ready to assist whenever needed."),
        ("en", "Thank you for the help Stewart.", "A pleasure as always, Illia. Do call if you require anything further."),
        ("ru", "Доброе утро, Стюарт.", "Доброе утро, сэр. Все системы активны и готовы к работе."),
        ("ru", "Как твои дела?", "Функционирую безупречно, сэр. Готов выполнять любые распоряжения."),
        ("ru", "Спасибо за помощь.", "Всегда к вашим услугам, Илья. Обращайтесь в любое время.")
    ]
    for lang, q, ans in dialogue_pairs:
        sys_p = sys_ru if lang == "ru" else sys_en
        augmented.append({
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": q},
                {"role": "assistant", "content": ans}
            ]
        })

    random.seed(42)
    random.shuffle(augmented)
    return augmented


def main():
    out_dir = Path(__file__).resolve().parent.parent / "data/dataset"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Generating enhanced 1.5B tool calling samples...")
    raw_samples = generate_all_samples()
    print(f"Generated {len(raw_samples)} unique tool calling samples.")

    tool_conversations = []
    for s in raw_samples:
        q = s["query"]
        tool_name = s.get("tool")
        tool_args = s.get("args")

        # Build compact candidate tool system prompt
        sys_prompt = build_compact_tool_prompt(tool_name, ALL_TOOLS)

        if tool_name is not None and tool_args is not None:
            tool_call_str = f"<tool_call>\n{json.dumps({'name': tool_name, 'arguments': tool_args}, ensure_ascii=False)}\n</tool_call>"
            msgs = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": q},
                {"role": "assistant", "content": tool_call_str}
            ]
        else:
            resp = s.get("response", "I am at your service, sir.")
            msgs = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": q},
                {"role": "assistant", "content": resp}
            ]
        tool_conversations.append({"messages": msgs})

    random.seed(42)
    random.shuffle(tool_conversations)

    split = int(len(tool_conversations) * 0.9)
    train_tool = tool_conversations[:split]
    val_tool = tool_conversations[split:]

    train_tool_file = out_dir / "train_1.5b.jsonl"
    val_tool_file = out_dir / "val_1.5b.jsonl"

    with open(train_tool_file, "w", encoding="utf-8") as f:
        for ex in train_tool:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    with open(val_tool_file, "w", encoding="utf-8") as f:
        for ex in val_tool:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"Wrote {len(train_tool)} tool training samples to {train_tool_file}")
    print(f"Wrote {len(val_tool)} tool validation samples to {val_tool_file}")

    # Generate Persona Dataset
    print("\nGenerating enhanced 1.5B persona samples...")
    persona_samples = generate_persona_samples()
    p_split = int(len(persona_samples) * 0.9)
    p_train = persona_samples[:p_split]
    p_val = persona_samples[p_split:]

    p_train_file = out_dir / "persona_train_1.5b.jsonl"
    p_val_file = out_dir / "persona_val_1.5b.jsonl"

    with open(p_train_file, "w", encoding="utf-8") as f:
        for ex in p_train:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    with open(p_val_file, "w", encoding="utf-8") as f:
        for ex in p_val:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"Wrote {len(p_train)} persona training samples to {p_train_file}")
    print(f"Wrote {len(p_val)} persona validation samples to {p_val_file}")

    # Update stewart_tools.json with all 24 tools
    tools_file = out_dir / "stewart_tools.json"
    tools_bak = out_dir / "stewart_tools_0.5b.json"
    if tools_file.exists() and not tools_bak.exists():
        import shutil
        shutil.copyfile(tools_file, tools_bak)
        print(f"Backed up 0.5B tools schema to {tools_bak}")

    with open(tools_file, "w", encoding="utf-8") as f:
        json.dump(ALL_TOOLS, f, ensure_ascii=False, indent=2)
    print(f"Updated {tools_file} with {len(ALL_TOOLS)} full tools.")


if __name__ == "__main__":
    main()
