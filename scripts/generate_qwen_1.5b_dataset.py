#!/usr/bin/env python3
"""
Massive Curated Bilingual Dataset Generator for Qwen2.5-1.5B Tool Calling.
Produces ~14,000 high-quality, nuanced training samples (~7,000 EN + ~7,000 RU).
Implements:
1. Categorical MCP-style tool calls (file, web, app, brightness, volume, music, hotkey, timer, system).
2. Deep semantic resolution (mapping entities to URLs/paths, colloquialisms like 'максимум' -> '100%').
3. Multi-turn situational follow-ups (e.g. open YouTube -> open search -> ctrl+f).
4. MCP Suites (Studieplus, Gmail, Study IB) + synthetic future MCP tools.
5. Strict negative chitchat rejection (direct text replies with zero tool hallucination).
6. Canonical sorted JSON serialization for minimal entropy and rapid convergence.
"""

import json
import random
from pathlib import Path
from typing import List, Dict, Any, Tuple

CATEGORICAL_TOOLS = [
    {
        "name": "web",
        "description": "Open website URLs or perform search queries in default web browser.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["open", "search"], "description": "Web action"},
                "url": {"type": "string", "description": "Website URL to open (e.g. https://wikipedia.org, https://youtube.com)"},
                "query": {"type": "string", "description": "Search query terms if searching"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "app",
        "description": "Launch, close, or switch desktop applications (terminal, browser, files, code, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["launch", "close", "switch"], "description": "Application action"},
                "name": {"type": "string", "description": "Application name or binary (e.g. kitty, terminal, files, telegram, code, youtube)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "file",
        "description": "Open, rename, or delete files and directories on the local Linux filesystem.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["open", "rename", "delete"], "description": "File action"},
                "path": {"type": "string", "description": "Target file or folder path (e.g. ~/Downloads, report.pdf)"},
                "new_name": {"type": "string", "description": "New filename when renaming"}
            },
            "required": ["action", "path"]
        }
    },
    {
        "name": "brightness",
        "description": "Adjust or set display screen brightness level.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "enum": ["set", "up", "down"], "description": "Brightness operation"},
                "value": {"type": "string", "description": "Brightness percentage or delta (e.g. 100%, 50%, 20%)"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "volume",
        "description": "Adjust or set master system volume level.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "enum": ["set", "up", "down", "mute", "unmute"], "description": "Volume operation"},
                "value": {"type": "string", "description": "Volume percentage or step (e.g. 80%, 50%, 15%)"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "music",
        "description": "Control music and media playback (pause, resume, play, next, previous, stop).",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["pause", "resume", "play", "next", "previous", "stop"], "description": "Playback action"},
                "track": {"type": "string", "description": "Song title or artist query when playing"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "hotkey",
        "description": "Send keyboard shortcut or hotkey combination to focused window.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["press"], "description": "Keypress action"},
                "keys": {"type": "array", "items": {"type": "string"}, "description": "List of keys (e.g. ['ctrl', 'f'], ['ctrl', 'w'])"}
            },
            "required": ["action", "keys"]
        }
    },
    {
        "name": "timer",
        "description": "Set, cancel or inspect countdown timers.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["set", "cancel", "status"], "description": "Timer action"},
                "duration": {"type": "string", "description": "Timer duration (e.g. 5 minutes, 30 seconds)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "system",
        "description": "System level operations: lock screen, check battery, tell time, weather, screenshot, or switch workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["lock", "battery", "time", "weather", "screenshot", "workspace"], "description": "System action"},
                "target": {"type": "string", "description": "Target argument (e.g. workspace number '2')"}
            },
            "required": ["action"]
        }
    }
]

MCP_TOOLS = [
    {
        "name": "studieplus_get_schedule",
        "description": "Fetch school timetable and class schedule for a specific day or week from Studieplus.",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {"type": "string", "description": "Target day (e.g. today, tomorrow, monday, next week)"}
            },
            "required": ["day"]
        }
    },
    {
        "name": "studieplus_get_assignments",
        "description": "Get homework, deadlines, and pending assignments from Studieplus.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "all", "upcoming"], "description": "Filter assignments by status"},
                "subject": {"type": "string", "description": "Optional school subject name (e.g. Math, Physics)"}
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
                "subject": {"type": "string", "description": "IB subject (e.g. Mathematics HL, Physics HL, Economics SL)"},
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
                "topic": {"type": "string", "description": "Subject or specific topic to practice (e.g. Calculus Derivatives, Wave Optics)"},
                "difficulty": {"type": "string", "enum": ["standard", "higher", "easy", "hard"], "description": "Level of difficulty"}
            },
            "required": ["topic"]
        }
    },
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
                "query": {"type": "string", "description": "Search query or sender name (e.g. from:Google, invoice)"},
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

SYNTHETIC_FUTURE_MCP_TOOLS = [
    {
        "name": "calendar_create_event",
        "description": "Create a new calendar entry with title, date, and start time.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title of event"},
                "date": {"type": "string", "description": "Event date (YYYY-MM-DD or 'tomorrow')"},
                "time": {"type": "string", "description": "Start time (HH:MM)"}
            },
            "required": ["title", "date"]
        }
    },
    {
        "name": "notes_create_note",
        "description": "Quickly create and save a markdown note.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title of note"},
                "content": {"type": "string", "description": "Body text of note"}
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "home_toggle_device",
        "description": "Turn on, off, or toggle a smart home device or light.",
        "parameters": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "Name of smart home device (e.g. desk light, bedroom fan)"},
                "state": {"type": "string", "enum": ["on", "off", "toggle"], "description": "Target power state"}
            },
            "required": ["device", "state"]
        }
    }
]

ALL_SYSTEM_TOOLS = CATEGORICAL_TOOLS + MCP_TOOLS + SYNTHETIC_FUTURE_MCP_TOOLS


def format_tool_schema(tools: List[Dict[str, Any]]) -> str:
    lines = []
    for t in tools:
        name = t["name"]
        desc = t.get("description", "")
        props = t.get("parameters", {}).get("properties", {})
        param_strs = []
        for pname, pinfo in sorted(props.items()):
            ptype = pinfo.get("type", "any")
            if "enum" in pinfo:
                ptype = "|".join(f'"{e}"' for e in pinfo["enum"])
            param_strs.append(f"{pname}: {ptype}")
        lines.append(f"- {name}({', '.join(param_strs)}) - {desc}")
    tools_block = "\n".join(lines)
    return (
        "You are Stewart, an intelligent Linux AI voice assistant on Hyprland.\n"
        "Available tools:\n"
        f"{tools_block}\n"
        "Call tools using: <tool_call>{\"arguments\": {...}, \"name\": \"...\"}</tool_call>.\n"
        "If no tool applies, answer directly."
    )


def make_tool_call(name: str, arguments: Dict[str, Any]) -> str:
    # Strict canonical format with sorted keys
    data = {
        "arguments": {k: arguments[k] for k in sorted(arguments.keys())},
        "name": name
    }
    return f"<tool_call>\n{json.dumps(data, ensure_ascii=False, sort_keys=True)}\n</tool_call>"


def pick_candidate_tools(target_tool_names: List[str], max_candidates: int = 10) -> List[Dict[str, Any]]:
    # Select candidate tools ensuring target tools are present + random distractors
    targets = [t for t in ALL_SYSTEM_TOOLS if t["name"] in target_tool_names]
    distractors = [t for t in ALL_SYSTEM_TOOLS if t["name"] not in target_tool_names]
    random.shuffle(distractors)
    needed = max_candidates - len(targets)
    candidates = targets + distractors[:max(0, needed)]
    random.shuffle(candidates)
    return candidates


# =========================================================================
# 1. Categorical Desktop Tools Generators
# =========================================================================

def gen_brightness_samples(is_ru: bool) -> List[Tuple[str, str, List[str]]]:
    samples = []
    levels = [
        ("10%", ["10 percent", "ten percent", "ten%"], ["10 процентов", "десять процентов", "на десять"]),
        ("25%", ["quarter", "25 percent"], ["на четверть", "двадцать пять процентов"]),
        ("50%", ["half", "halfway", "50 percent", "medium"], ["наполовину", "на 50 процентов", "среднюю яркость"]),
        ("75%", ["75 percent", "three quarters"], ["на семьдесят пять процентов", "три четверти"]),
        ("80%", ["80 percent", "eighty"], ["80 процентов", "на восемьдесят"]),
        ("100%", ["maximum", "max", "full brightness", "hundred percent"], ["максимум", "на максимум", "на полную", "сто процентов"])
    ]
    deltas = [
        ("10%", ["a bit", "a little", "10 percent"], ["чуть-чуть", "немного", "на десять процентов"]),
        ("15%", ["slightly", "a little bit", "15%"], ["слегка", "на 15 процентов"]),
        ("20%", ["a notch", "20 percent"], ["на двадцать процентов", "посильнее"]),
    ]

    for val, en_phrases, ru_phrases in levels:
        if is_ru:
            for p in ru_phrases:
                for verb in ["поставь яркость ", "сделай яркость ", "яркость ", "установи яркость "]:
                    samples.append((f"{verb}{p}", make_tool_call("brightness", {"command": "set", "value": val}), ["brightness"]))
        else:
            for p in en_phrases:
                for verb in ["set brightness to ", "make brightness ", "brightness ", "adjust brightness to "]:
                    samples.append((f"{verb}{p}", make_tool_call("brightness", {"command": "set", "value": val}), ["brightness"]))

    for val, en_phrases, ru_phrases in deltas:
        if is_ru:
            for p in ru_phrases:
                samples.append((f"сделай поярче {p}", make_tool_call("brightness", {"command": "up", "value": val}), ["brightness"]))
                samples.append((f"прибавь яркость {p}", make_tool_call("brightness", {"command": "up", "value": val}), ["brightness"]))
                samples.append((f"сделай потемнее {p}", make_tool_call("brightness", {"command": "down", "value": val}), ["brightness"]))
                samples.append((f"убавь яркость {p}", make_tool_call("brightness", {"command": "down", "value": val}), ["brightness"]))
                samples.append((f"приглуши экран {p}", make_tool_call("brightness", {"command": "down", "value": val}), ["brightness"]))
        else:
            for p in en_phrases:
                samples.append((f"make it brighter {p}", make_tool_call("brightness", {"command": "up", "value": val}), ["brightness"]))
                samples.append((f"turn up brightness {p}", make_tool_call("brightness", {"command": "up", "value": val}), ["brightness"]))
                samples.append((f"dim screen {p}", make_tool_call("brightness", {"command": "down", "value": val}), ["brightness"]))
                samples.append((f"make it darker {p}", make_tool_call("brightness", {"command": "down", "value": val}), ["brightness"]))
                samples.append((f"lower brightness {p}", make_tool_call("brightness", {"command": "down", "value": val}), ["brightness"]))

    return samples


def gen_volume_samples(is_ru: bool) -> List[Tuple[str, str, List[str]]]:
    samples = []
    levels = [
        ("0%", ["zero", "0 percent"], ["ноль", "на ноль"]),
        ("20%", ["twenty percent", "20%"], ["двадцать процентов", "на 20"]),
        ("40%", ["forty percent", "40%"], ["сорок процентов", "на сорок"]),
        ("50%", ["half", "half volume", "50 percent"], ["наполовину", "на 50 процентов"]),
        ("80%", ["eighty percent", "80%"], ["восемьдесят процентов", "на восемьдесят"]),
        ("100%", ["max volume", "maximum", "full volume", "hundred percent"], ["на максимум", "максимальная громкость", "на полную"])
    ]
    deltas = [
        ("10%", ["a bit", "a little", "10%"], ["чуть-чуть", "немного", "на десять"]),
        ("15%", ["a little bit", "15%"], ["слегка", "на пятнадцать"]),
        ("20%", ["a notch", "20%"], ["посильнее", "на двадцать"])
    ]

    for val, en_phrases, ru_phrases in levels:
        if is_ru:
            for p in ru_phrases:
                for v in ["громкость ", "поставь звук ", "сделай громкость ", "звук "]:
                    samples.append((f"{v}{p}", make_tool_call("volume", {"command": "set", "value": val}), ["volume"]))
        else:
            for p in en_phrases:
                for v in ["set volume to ", "volume to ", "make volume ", "sound to "]:
                    samples.append((f"{v}{p}", make_tool_call("volume", {"command": "set", "value": val}), ["volume"]))

    for val, en_phrases, ru_phrases in deltas:
        if is_ru:
            for p in ru_phrases:
                samples.append((f"сделай погромче {p}", make_tool_call("volume", {"command": "up", "value": val}), ["volume"]))
                samples.append((f"прибавь звук {p}", make_tool_call("volume", {"command": "up", "value": val}), ["volume"]))
                samples.append((f"сделай потише {p}", make_tool_call("volume", {"command": "down", "value": val}), ["volume"]))
                samples.append((f"убавь звук {p}", make_tool_call("volume", {"command": "down", "value": val}), ["volume"]))
        else:
            for p in en_phrases:
                samples.append((f"make it louder {p}", make_tool_call("volume", {"command": "up", "value": val}), ["volume"]))
                samples.append((f"turn up sound {p}", make_tool_call("volume", {"command": "up", "value": val}), ["volume"]))
                samples.append((f"make it quieter {p}", make_tool_call("volume", {"command": "down", "value": val}), ["volume"]))
                samples.append((f"lower the volume {p}", make_tool_call("volume", {"command": "down", "value": val}), ["volume"]))

    # Mute / Unmute
    if is_ru:
        for p in ["выключи звук", "заглуши", "без звука", "выруби звук", "отключи аудио"]:
            samples.append((p, make_tool_call("volume", {"command": "mute"}), ["volume"]))
        for p in ["включи звук обратно", "разглуши", "верни звук", "включи звук"]:
            samples.append((p, make_tool_call("volume", {"command": "unmute"}), ["volume"]))
    else:
        for p in ["mute", "mute sound", "silence audio", "shut up", "turn off volume"]:
            samples.append((p, make_tool_call("volume", {"command": "mute"}), ["volume"]))
        for p in ["unmute", "unmute sound", "restore sound", "bring back sound"]:
            samples.append((p, make_tool_call("volume", {"command": "unmute"}), ["volume"]))

    return samples


def gen_web_and_app_samples(is_ru: bool) -> List[Tuple[str, str, List[str]]]:
    samples = []
    # Semantic web mappings
    web_targets = [
        ("https://wikipedia.org", ["wikipedia", "open wikipedia"], ["википедию", "открой википедию"]),
        ("https://youtube.com", ["youtube", "open youtube"], ["ютуб", "открой ютуб"]),
        ("https://github.com", ["github", "open github"], ["гитхаб", "открой гитхаб"]),
        ("https://reddit.com", ["reddit", "open reddit"], ["реддит", "открой реддит"]),
        ("https://google.com", ["google", "open google"], ["гугл", "открой гугл"]),
        ("https://chatgpt.com", ["chatgpt", "open chatgpt"], ["чат гпт", "открой chatgpt"]),
        ("https://mail.google.com", ["webmail", "gmail in browser"], ["почту в браузере", "открой gmail веб"]),
        ("https://twitch.tv", ["twitch", "open twitch"], ["твич", "открой twitch"])
    ]

    for url, en_list, ru_list in web_targets:
        if is_ru:
            for p in ru_list:
                for prefix in ["", "пожалуйста ", "стюарт "]:
                    samples.append((f"{prefix}{p}", make_tool_call("web", {"action": "open", "url": url}), ["web"]))
        else:
            for p in en_list:
                for prefix in ["", "please ", "stewart "]:
                    samples.append((f"{prefix}{p}", make_tool_call("web", {"action": "open", "url": url}), ["web"]))

    # Web search
    searches = [
        ("how to install nixos on thinkpad", ["search google for how to install nixos on thinkpad", "google how to install nixos on thinkpad"], ["найди в гугле как установить nixos на thinkpad", "поищи как установить nixos на thinkpad"]),
        ("weather in tokyo next week", ["google weather in tokyo next week", "search web for weather in tokyo next week"], ["поищи в интернете погода в токио на следующей неделе", "найди погоду в токио"]),
        ("python async await tutorial", ["search web for python async await tutorial"], ["найди руководство по python async await"]),
        ("hyprland config examples", ["google hyprland config examples"], ["поищи примеры конфига hyprland"])
    ]
    for q, en_list, ru_list in searches:
        if is_ru:
            for p in ru_list:
                samples.append((p, make_tool_call("web", {"action": "search", "query": q}), ["web"]))
        else:
            for p in en_list:
                samples.append((p, make_tool_call("web", {"action": "search", "query": q}), ["web"]))

    # Apps
    apps = [
        ("terminal", ["open terminal", "launch console", "open kitty", "start terminal"], ["открой терминал", "запусти консоль", "открой китти"]),
        ("telegram", ["launch telegram", "open telegram"], ["открой телеграм", "запусти телеграм"]),
        ("files", ["open file manager", "open files", "launch nautilus"], ["открой файловый менеджер", "открой файлы", "запусти наутилус"]),
        ("code", ["open vs code", "launch code editor", "start vscode"], ["открой visual studio code", "запусти редактор кода", "открой вскод"]),
        ("spotify", ["launch spotify", "open spotify"], ["запусти спотифай", "открой спотифай"]),
        ("browser", ["open browser", "launch chrome", "open brave"], ["открой браузер", "запусти хром"]),
        ("discord", ["launch discord", "open discord"], ["открой дискорд", "запусти дискорд"]),
        ("settings", ["open system settings", "launch settings"], ["открой настройки", "запусти параметры"])
    ]
    for app_name, en_list, ru_list in apps:
        if is_ru:
            for p in ru_list:
                for prefix in ["", "пожалуйста ", "стюарт "]:
                    samples.append((f"{prefix}{p}", make_tool_call("app", {"action": "launch", "name": app_name}), ["app"]))
        else:
            for p in en_list:
                for prefix in ["", "please ", "stewart "]:
                    samples.append((f"{prefix}{p}", make_tool_call("app", {"action": "launch", "name": app_name}), ["app"]))

    # App close & switch
    if is_ru:
        for p in ["закрой окно", "закрой эту программу", "закрой активное окно", "закрой приложение"]:
            samples.append((p, make_tool_call("app", {"action": "close"}), ["app"]))
        for p in ["переключись на браузер", "перейди в браузер"]:
            samples.append((p, make_tool_call("app", {"action": "switch", "name": "browser"}), ["app"]))
        for p in ["переключись на терминал", "перейди в консоль"]:
            samples.append((p, make_tool_call("app", {"action": "switch", "name": "terminal"}), ["app"]))
    else:
        for p in ["close window", "close this application", "close active window", "exit app"]:
            samples.append((p, make_tool_call("app", {"action": "close"}), ["app"]))
        for p in ["switch to browser", "focus browser"]:
            samples.append((p, make_tool_call("app", {"action": "switch", "name": "browser"}), ["app"]))
        for p in ["switch to terminal", "focus terminal"]:
            samples.append((p, make_tool_call("app", {"action": "switch", "name": "terminal"}), ["app"]))

    return samples


def gen_file_samples(is_ru: bool) -> List[Tuple[str, str, List[str]]]:
    samples = []
    file_open = [
        ("~/Downloads", ["open downloads", "open my downloads folder"], ["открой папку загрузки", "открой загрузки", "покажи загрузки"]),
        ("~/Documents", ["open documents", "open documents directory"], ["открой документы", "открой папку документы"]),
        ("~/Pictures", ["open pictures", "open screenshots folder"], ["открой картинки", "открой изображения"]),
        ("~/Projects", ["open projects folder", "open my code folder"], ["открой папку с проектами", "открой проекты"]),
        ("report.pdf", ["open report.pdf", "open the report document"], ["открой report.pdf", "открой отчет"]),
        ("physics_notes.txt", ["open physics_notes.txt", "open notes"], ["открой конспект по физике", "открой physics_notes.txt"]),
        ("presentation.pptx", ["open presentation.pptx", "open the slides"], ["открой презентацию", "открой presentation.pptx"])
    ]
    for path, en_list, ru_list in file_open:
        if is_ru:
            for p in ru_list:
                samples.append((p, make_tool_call("file", {"action": "open", "path": path}), ["file"]))
        else:
            for p in en_list:
                samples.append((p, make_tool_call("file", {"action": "open", "path": path}), ["file"]))

    # Renames
    if is_ru:
        samples.append(("переименуй draft.txt в final.txt", make_tool_call("file", {"action": "rename", "new_name": "final.txt", "path": "draft.txt"}), ["file"]))
        samples.append(("переименуй photo.jpg в avatar.jpg", make_tool_call("file", {"action": "rename", "new_name": "avatar.jpg", "path": "photo.jpg"}), ["file"]))
        samples.append(("переименуй old_notes.md в notes.md", make_tool_call("file", {"action": "rename", "new_name": "notes.md", "path": "old_notes.md"}), ["file"]))
    else:
        samples.append(("rename draft.txt to final.txt", make_tool_call("file", {"action": "rename", "new_name": "final.txt", "path": "draft.txt"}), ["file"]))
        samples.append(("rename photo.jpg to avatar.jpg", make_tool_call("file", {"action": "rename", "new_name": "avatar.jpg", "path": "photo.jpg"}), ["file"]))
        samples.append(("rename old_notes.md to notes.md", make_tool_call("file", {"action": "rename", "new_name": "notes.md", "path": "old_notes.md"}), ["file"]))

    return samples


def gen_music_and_hotkey_samples(is_ru: bool) -> List[Tuple[str, str, List[str]]]:
    samples = []
    # Music actions
    if is_ru:
        for p in ["поставь на паузу", "пауза", "останови музыку", "пауза в треке", "музыку на паузу"]:
            samples.append((p, make_tool_call("music", {"action": "pause"}), ["music"]))
        for p in ["продолжи музыку", "сними с паузы", "возобнови трек", "играй дальше"]:
            samples.append((p, make_tool_call("music", {"action": "resume"}), ["music"]))
        for p in ["следующий трек", "переключи песню", "следующая песня", "скипни трек"]:
            samples.append((p, make_tool_call("music", {"action": "next"}), ["music"]))
        for p in ["предыдущий трек", "верни песню", "прошлый трек"]:
            samples.append((p, make_tool_call("music", {"action": "previous"}), ["music"]))
        for p in ["останови воспроизведение", "выключи музыку", "стоп музыка"]:
            samples.append((p, make_tool_call("music", {"action": "stop"}), ["music"]))
        for track in ["queen bohemian rhapsody", "daft punk get lucky", "lo-fi beats", "hans zimmer interstellar"]:
            samples.append((f"включи {track}", make_tool_call("music", {"action": "play", "track": track}), ["music"]))
            samples.append((f"поставь песню {track}", make_tool_call("music", {"action": "play", "track": track}), ["music"]))
    else:
        for p in ["pause music", "pause playback", "stop track", "pause the song", "music pause"]:
            samples.append((p, make_tool_call("music", {"action": "pause"}), ["music"]))
        for p in ["resume music", "continue playback", "unpause", "play music again"]:
            samples.append((p, make_tool_call("music", {"action": "resume"}), ["music"]))
        for p in ["next song", "skip track", "next track", "skip this song"]:
            samples.append((p, make_tool_call("music", {"action": "next"}), ["music"]))
        for p in ["previous song", "last track", "previous track", "go back a track"]:
            samples.append((p, make_tool_call("music", {"action": "previous"}), ["music"]))
        for p in ["stop music", "halt playback", "stop audio"]:
            samples.append((p, make_tool_call("music", {"action": "stop"}), ["music"]))
        for track in ["queen bohemian rhapsody", "daft punk get lucky", "lofi hip hop radio", "interstellar theme"]:
            samples.append((f"play {track}", make_tool_call("music", {"action": "play", "track": track}), ["music"]))
            samples.append((f"put on {track}", make_tool_call("music", {"action": "play", "track": track}), ["music"]))

    # Hotkeys
    hotkey_pairs = [
        (["ctrl", "w"], ["close tab", "close this tab"], ["закрой вкладку", "закрой эту вкладку"]),
        (["ctrl", "t"], ["new tab", "open a new tab"], ["новая вкладка", "открой новую вкладку"]),
        (["ctrl", "c"], ["copy this", "copy selection"], ["скопируй", "скопируй выделенное"]),
        (["ctrl", "v"], ["paste clipboard", "paste here"], ["вставь", "вставь из буфера"]),
        (["ctrl", "s"], ["save file", "save document"], ["сохрани файл", "сохрани документ"]),
        (["ctrl", "f"], ["search in page", "find text"], ["поиск по странице", "найди на странице"]),
        (["ctrl", "z"], ["undo that", "undo last change"], ["отмени действие", "откат назад"]),
        (["ctrl", "shift", "z"], ["redo that", "redo"], ["повтори действие", "верни вперед"]),
        (["alt", "tab"], ["switch window", "next window"], ["переключи окно", "следующее окно"]),
        (["ctrl", "l"], ["focus address bar", "clear screen"], ["очисти экран", "перейди в адресную строку"])
    ]
    for keys, en_list, ru_list in hotkey_pairs:
        if is_ru:
            for p in ru_list:
                samples.append((p, make_tool_call("hotkey", {"action": "press", "keys": keys}), ["hotkey"]))
        else:
            for p in en_list:
                samples.append((p, make_tool_call("hotkey", {"action": "press", "keys": keys}), ["hotkey"]))

    return samples


def gen_system_and_timer_samples(is_ru: bool) -> List[Tuple[str, str, List[str]]]:
    samples = []
    # Timer
    durations = [
        ("1 minute", ["1 minute", "one minute"], ["1 минуту", "одну минуту"]),
        ("5 minutes", ["5 minutes", "five minutes"], ["5 минут", "пять минут"]),
        ("10 minutes", ["10 minutes", "ten minutes"], ["10 минут", "десять минут"]),
        ("15 minutes", ["15 minutes", "fifteen minutes"], ["15 минут", "пятнадцать минут"]),
        ("25 minutes", ["25 minutes", "pomodoro timer"], ["25 минут", "помидор"]),
        ("30 seconds", ["30 seconds", "half a minute"], ["30 секунд", "полминуты"]),
        ("1 hour", ["1 hour", "one hour"], ["1 час", "один час"])
    ]
    for dur, en_list, ru_list in durations:
        if is_ru:
            for p in ru_list:
                samples.append((f"поставь таймер на {p}", make_tool_call("timer", {"action": "set", "duration": dur}), ["timer"]))
                samples.append((f"засеки {p}", make_tool_call("timer", {"action": "set", "duration": dur}), ["timer"]))
        else:
            for p in en_list:
                samples.append((f"set timer for {p}", make_tool_call("timer", {"action": "set", "duration": dur}), ["timer"]))
                samples.append((f"start a {p} timer", make_tool_call("timer", {"action": "set", "duration": dur}), ["timer"]))

    if is_ru:
        for p in ["отмени таймер", "сбрось таймер", "выключи таймер"]:
            samples.append((p, make_tool_call("timer", {"action": "cancel"}), ["timer"]))
        for p in ["сколько осталось на таймере", "статус таймера", "покажи таймер"]:
            samples.append((p, make_tool_call("timer", {"action": "status"}), ["timer"]))
    else:
        for p in ["cancel timer", "stop timer", "reset the timer"]:
            samples.append((p, make_tool_call("timer", {"action": "cancel"}), ["timer"]))
        for p in ["how much time left on timer", "timer status", "check timer"]:
            samples.append((p, make_tool_call("timer", {"action": "status"}), ["timer"]))

    # System operations
    if is_ru:
        for p in ["заблокируй экран", "заблокируй сессию", "залочь компьютер", "заблокируй систему"]:
            samples.append((p, make_tool_call("system", {"action": "lock"}), ["system"]))
        for p in ["сколько батареи", "проверь заряд аккумулятора", "какой заряд батареи", "уровень заряда"]:
            samples.append((p, make_tool_call("system", {"action": "battery"}), ["system"]))
        for p in ["который час", "сколько сейчас времени", "скажи время", "текущее время"]:
            samples.append((p, make_tool_call("system", {"action": "time"}), ["system"]))
        for p in ["какая сейчас погода", "скажи погоду", "погода на улице"]:
            samples.append((p, make_tool_call("system", {"action": "weather"}), ["system"]))
        for p in ["сделай скриншот", "сделай снимок экрана", "сфоткай экран"]:
            samples.append((p, make_tool_call("system", {"action": "screenshot"}), ["system"]))
        for ws in ["1", "2", "3", "4", "5"]:
            samples.append((f"переключись на воркспейс {ws}", make_tool_call("system", {"action": "workspace", "target": ws}), ["system"]))
            samples.append((f"перейди на рабочий стол {ws}", make_tool_call("system", {"action": "workspace", "target": ws}), ["system"]))
    else:
        for p in ["lock screen", "lock computer", "lock session", "lock my desktop"]:
            samples.append((p, make_tool_call("system", {"action": "lock"}), ["system"]))
        for p in ["check battery", "how much battery is left", "battery status", "what is battery percentage"]:
            samples.append((p, make_tool_call("system", {"action": "battery"}), ["system"]))
        for p in ["what time is it", "tell me the time", "current time", "what's the time"]:
            samples.append((p, make_tool_call("system", {"action": "time"}), ["system"]))
        for p in ["what's the weather", "tell weather forecast", "weather outside"]:
            samples.append((p, make_tool_call("system", {"action": "weather"}), ["system"]))
        for p in ["take a screenshot", "capture screen", "screenshot"]:
            samples.append((p, make_tool_call("system", {"action": "screenshot"}), ["system"]))
        for ws in ["1", "2", "3", "4", "5"]:
            samples.append((f"switch to workspace {ws}", make_tool_call("system", {"action": "workspace", "target": ws}), ["system"]))
            samples.append((f"go to workspace {ws}", make_tool_call("system", {"action": "workspace", "target": ws}), ["system"]))

    return samples


def gen_mcp_samples(is_ru: bool) -> List[Tuple[str, str, List[str]]]:
    samples = []
    # Studieplus
    days = [("today", "сегодня"), ("tomorrow", "завтра"), ("monday", "понедельник"), ("next week", "следующую неделю")]
    for en_d, ru_d in days:
        if is_ru:
            samples.append((f"расписание на {ru_d}", make_tool_call("studieplus_get_schedule", {"day": en_d}), ["studieplus_get_schedule"]))
            samples.append((f"покажи уроки на {ru_d}", make_tool_call("studieplus_get_schedule", {"day": en_d}), ["studieplus_get_schedule"]))
        else:
            samples.append((f"schedule for {en_d}", make_tool_call("studieplus_get_schedule", {"day": en_d}), ["studieplus_get_schedule"]))
            samples.append((f"timetable for {en_d}", make_tool_call("studieplus_get_schedule", {"day": en_d}), ["studieplus_get_schedule"]))

    if is_ru:
        samples.append(("какие у меня домашние задания", make_tool_call("studieplus_get_assignments", {"status": "pending"}), ["studieplus_get_assignments"]))
        samples.append(("домашнее задание по физике", make_tool_call("studieplus_get_assignments", {"status": "all", "subject": "Physics"}), ["studieplus_get_assignments"]))
        samples.append(("сообщения от учителей", make_tool_call("studieplus_get_conversations", {}), ["studieplus_get_conversations"]))
        samples.append(("проверь сессию studieplus", make_tool_call("studieplus_check_session", {}), ["studieplus_check_session"]))
    else:
        samples.append(("check pending assignments", make_tool_call("studieplus_get_assignments", {"status": "pending"}), ["studieplus_get_assignments"]))
        samples.append(("homework for physics", make_tool_call("studieplus_get_assignments", {"status": "all", "subject": "Physics"}), ["studieplus_get_assignments"]))
        samples.append(("check teacher messages", make_tool_call("studieplus_get_conversations", {}), ["studieplus_get_conversations"]))
        samples.append(("is studieplus session active", make_tool_call("studieplus_check_session", {}), ["studieplus_check_session"]))

    # IB Study
    if is_ru:
        samples.append(("материалы по ib physics past papers", make_tool_call("study_get_ib_resources", {"resource_type": "past_papers", "subject": "Physics HL"}), ["study_get_ib_resources"]))
        samples.append(("вопросы для теста по calculus", make_tool_call("study_prepare_test", {"difficulty": "standard", "topic": "Calculus Derivatives"}), ["study_prepare_test"]))
    else:
        samples.append(("get ib past papers for physics hl", make_tool_call("study_get_ib_resources", {"resource_type": "past_papers", "subject": "Physics HL"}), ["study_get_ib_resources"]))
        samples.append(("prepare practice test for calculus derivatives", make_tool_call("study_prepare_test", {"difficulty": "standard", "topic": "Calculus Derivatives"}), ["study_prepare_test"]))

    # Gmail
    if is_ru:
        samples.append(("проверь непрочитанные письма", make_tool_call("gmail_check_status", {}), ["gmail_check_status"]))
        samples.append(("найди письмо от google", make_tool_call("gmail_search_emails", {"max_results": 5, "query": "from:Google"}), ["gmail_search_emails"]))
        samples.append(("найди письма со словом счет", make_tool_call("gmail_search_emails", {"max_results": 5, "query": "счет"}), ["gmail_search_emails"]))
        samples.append(("отправь письмо teacher@school.com с темой Отчет и текстом Готово", make_tool_call("gmail_send_email", {"body": "Готово", "subject": "Отчет", "to": "teacher@school.com"}), ["gmail_send_email"]))
    else:
        samples.append(("check unread emails in gmail", make_tool_call("gmail_check_status", {}), ["gmail_check_status"]))
        samples.append(("search emails from google", make_tool_call("gmail_search_emails", {"max_results": 5, "query": "from:Google"}), ["gmail_search_emails"]))
        samples.append(("find invoice emails", make_tool_call("gmail_search_emails", {"max_results": 5, "query": "invoice"}), ["gmail_search_emails"]))
        samples.append(("send email to teacher@school.com subject Homework body Here is my submission", make_tool_call("gmail_send_email", {"body": "Here is my submission", "subject": "Homework", "to": "teacher@school.com"}), ["gmail_send_email"]))

    # Synthetic Future MCP
    if is_ru:
        samples.append(("создай встречу Встреча с куратором на завтра в 15:00", make_tool_call("calendar_create_event", {"date": "tomorrow", "time": "15:00", "title": "Встреча с куратором"}), ["calendar_create_event"]))
        samples.append(("сохрани заметку Идеи с текстом Купить книгу", make_tool_call("notes_create_note", {"content": "Купить книгу", "title": "Идеи"}), ["notes_create_note"]))
        samples.append(("включи настольную лампу", make_tool_call("home_toggle_device", {"device": "настольная лампа", "state": "on"}), ["home_toggle_device"]))
    else:
        samples.append(("create calendar event Meeting with tutor tomorrow at 15:00", make_tool_call("calendar_create_event", {"date": "tomorrow", "time": "15:00", "title": "Meeting with tutor"}), ["calendar_create_event"]))
        samples.append(("save note Ideas with content Buy textbook", make_tool_call("notes_create_note", {"content": "Buy textbook", "title": "Ideas"}), ["notes_create_note"]))
        samples.append(("turn on desk lamp", make_tool_call("home_toggle_device", {"device": "desk lamp", "state": "on"}), ["home_toggle_device"]))

    return samples


def gen_multiturn_samples(is_ru: bool) -> List[Dict[str, Any]]:
    conversations = []
    # Pattern 1: YouTube context -> Follow-ups
    if is_ru:
        conversations.append({
            "tools": ["web", "hotkey", "music", "app"],
            "dialog": [
                ("открой ютуб", make_tool_call("web", {"action": "open", "url": "https://youtube.com"})),
                ("включи поиск", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "f"]})),
                ("сделай на весь экран", make_tool_call("hotkey", {"action": "press", "keys": ["f"]})),
                ("поставь на паузу", make_tool_call("music", {"action": "pause"}))
            ]
        })
        conversations.append({
            "tools": ["app", "hotkey"],
            "dialog": [
                ("открой терминал", make_tool_call("app", {"action": "launch", "name": "terminal"})),
                ("найди команду", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "r"]})),
                ("очисти экран", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "l"]})),
                ("закрой консоль", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "d"]}))
            ]
        })
        conversations.append({
            "tools": ["file", "hotkey"],
            "dialog": [
                ("открой папку загрузки", make_tool_call("file", {"action": "open", "path": "~/Downloads"})),
                ("найди файл", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "f"]})),
                ("закрой окно", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "w"]}))
            ]
        })
        conversations.append({
            "tools": ["app", "hotkey"],
            "dialog": [
                ("запусти редактор кода", make_tool_call("app", {"action": "launch", "name": "code"})),
                ("сохрани файл", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "s"]})),
                ("закрой вкладку", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "w"]}))
            ]
        })
    else:
        conversations.append({
            "tools": ["web", "hotkey", "music", "app"],
            "dialog": [
                ("open youtube", make_tool_call("web", {"action": "open", "url": "https://youtube.com"})),
                ("open search", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "f"]})),
                ("full screen", make_tool_call("hotkey", {"action": "press", "keys": ["f"]})),
                ("pause playback", make_tool_call("music", {"action": "pause"}))
            ]
        })
        conversations.append({
            "tools": ["app", "hotkey"],
            "dialog": [
                ("launch terminal", make_tool_call("app", {"action": "launch", "name": "terminal"})),
                ("search history", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "r"]})),
                ("clear screen", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "l"]})),
                ("exit terminal", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "d"]}))
            ]
        })
        conversations.append({
            "tools": ["file", "hotkey"],
            "dialog": [
                ("open my downloads folder", make_tool_call("file", {"action": "open", "path": "~/Downloads"})),
                ("find file", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "f"]})),
                ("close it", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "w"]}))
            ]
        })
        conversations.append({
            "tools": ["app", "hotkey"],
            "dialog": [
                ("launch vs code", make_tool_call("app", {"action": "launch", "name": "code"})),
                ("save file", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "s"]})),
                ("close tab", make_tool_call("hotkey", {"action": "press", "keys": ["ctrl", "w"]}))
            ]
        })

    samples = []
    # Build incremental dialog states
    for conv in conversations:
        dialog = conv["dialog"]
        tool_names = conv["tools"]
        cand_tools = pick_candidate_tools(tool_names)
        sys_prompt = format_tool_schema(cand_tools)

        messages = [{"role": "system", "content": sys_prompt}]
        for u_text, a_resp in dialog:
            messages.append({"role": "user", "content": u_text})
            samples.append({"messages": list(messages + [{"role": "assistant", "content": a_resp}])})
            messages.append({"role": "assistant", "content": a_resp})

    return samples


def gen_chitchat_samples(is_ru: bool) -> List[Tuple[str, str, List[str]]]:
    samples = []
    if is_ru:
        pairs = [
            ("привет", "Здравствуйте! Чем могу помочь вам сегодня?"),
            ("доброе утро", "Доброе утро! Готов к вашим распоряжениям."),
            ("как твои дела", "Все системы функционируют в штатном режиме, спасибо."),
            ("кто тебя создал", "Я Стюарт, персональный голосовой ассистент на Linux под управлением Hyprland."),
            ("что такое квантовая запутанность", "Квантовая запутанность — это физическое явление, при котором квантовые состояния двух или более объектов оказываются взаимозависимыми."),
            ("сколько будет 25 умножить на 4", "25 умножить на 4 будет 100."),
            ("расскажи шутку", "Почему программисты путают Хэллоуин и Рождество? Потому что 31 Oct равно 25 Dec."),
            ("спасибо за помощь", "Всегда рад служить! Обращайтесь в любое время."),
            ("что ты умеешь", "Я умею управлять рабочим столом Hyprland, настраивать громкость и яркость, запускать приложения, открывать веб-сайты, проверять расписание в Studieplus и почту Gmail.")
        ]
    else:
        pairs = [
            ("hello", "Good day, sir! How may I assist you today?"),
            ("good morning", "Good morning! All systems are operational and standing by."),
            ("how are you doing", "Operating at peak efficiency, thank you."),
            ("who created you", "I am Stewart, your personal AI voice assistant running on NixOS and Hyprland."),
            ("what is entropy", "Entropy is a measure of the degree of randomness or disorder in a closed thermodynamic system."),
            ("what is 15 times 6", "15 multiplied by 6 is 90."),
            ("tell me a joke", "There are only 10 types of people in the world: those who understand binary, and those who don't."),
            ("thank you for your help", "My pleasure, sir. Always at your service."),
            ("what can you do", "I can manage your Hyprland desktop, adjust audio and display brightness, launch applications, browse websites, check Studieplus school timetable, and search Gmail.")
        ]

    for q, ans in pairs:
        for prefix in ["", "hey stewart ", "please ", "эй стюарт ", "пожалуйста "]:
            if is_ru and any(c in prefix for c in ["hey", "please"]):
                continue
            if not is_ru and any(c in prefix for c in ["эй", "пожалуйста"]):
                continue
            samples.append((f"{prefix}{q}", ans, []))

    return samples


# =========================================================================
# Main Synthesis & Amplification Engine (Aim: ~7,000 EN + ~7,000 RU)
# =========================================================================

EN_PREFIXES = ["", "please ", "stewart ", "hey stewart ", "could you ", "can you ", "go ahead and ", "just "]
RU_PREFIXES = ["", "пожалуйста ", "стюарт ", "эй стюарт ", "можешь ", "сделай ", "просто "]


def build_augmented_dataset(is_ru: bool, target_count: int = 7000) -> List[Dict[str, Any]]:
    raw_triplets: List[Tuple[str, str, List[str]]] = []

    raw_triplets.extend(gen_brightness_samples(is_ru))
    raw_triplets.extend(gen_volume_samples(is_ru))
    raw_triplets.extend(gen_web_and_app_samples(is_ru))
    raw_triplets.extend(gen_file_samples(is_ru))
    raw_triplets.extend(gen_music_and_hotkey_samples(is_ru))
    raw_triplets.extend(gen_system_and_timer_samples(is_ru))
    raw_triplets.extend(gen_mcp_samples(is_ru))
    raw_triplets.extend(gen_chitchat_samples(is_ru))

    prefixes = RU_PREFIXES if is_ru else EN_PREFIXES

    final_examples = []

    # 1. Multi-turn samples directly injected
    multiturn_samples = gen_multiturn_samples(is_ru)
    # Multiply multiturn samples to ensure strong presence (~1,500 samples)
    for _ in range(35):
        for ms in multiturn_samples:
            final_examples.append(ms)

    # 2. Augment and package raw triplets
    while len(final_examples) < target_count:
        triplet = random.choice(raw_triplets)
        query, response, needed_tools = triplet
        prefix = random.choice(prefixes)
        augmented_query = f"{prefix}{query}".strip()

        # Build dynamic candidate tool list
        cand_tools = pick_candidate_tools(needed_tools, max_candidates=random.randint(6, 12))
        sys_prompt = format_tool_schema(cand_tools)

        example = {
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": augmented_query},
                {"role": "assistant", "content": response}
            ]
        }
        final_examples.append(example)

    random.shuffle(final_examples)
    return final_examples[:target_count]


def main():
    print("=== Generating Stewart 14,000 Curated Bilingual Dataset ===")
    dataset_dir = Path("data/dataset")
    dataset_dir.mkdir(parents=True, exist_ok=True)

    print("Generating English dataset (~7,000 samples)...")
    en_samples = build_augmented_dataset(is_ru=False, target_count=7000)
    val_split_en = int(len(en_samples) * 0.10)
    train_en = en_samples[val_split_en:]
    val_en = en_samples[:val_split_en]

    with open(dataset_dir / "train_en.jsonl", "w", encoding="utf-8") as f:
        for ex in train_en:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    with open(dataset_dir / "val_en.jsonl", "w", encoding="utf-8") as f:
        for ex in val_en:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"English: Train={len(train_en)}, Val={len(val_en)}")

    print("Generating Russian dataset (~7,000 samples)...")
    ru_samples = build_augmented_dataset(is_ru=True, target_count=7000)
    val_split_ru = int(len(ru_samples) * 0.10)
    train_ru = ru_samples[val_split_ru:]
    val_ru = ru_samples[:val_split_ru]

    with open(dataset_dir / "train_ru.jsonl", "w", encoding="utf-8") as f:
        for ex in train_ru:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    with open(dataset_dir / "val_ru.jsonl", "w", encoding="utf-8") as f:
        for ex in val_ru:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"Russian: Train={len(train_ru)}, Val={len(val_ru)}")

    # Combined 14k dataset for unified training & benchmark
    combined_train = train_en + train_ru
    combined_val = val_en + val_ru
    random.shuffle(combined_train)
    random.shuffle(combined_val)

    with open(dataset_dir / "train_1.5b.jsonl", "w", encoding="utf-8") as f:
        for ex in combined_train:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    with open(dataset_dir / "val_1.5b.jsonl", "w", encoding="utf-8") as f:
        for ex in combined_val:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"Combined 14k Dataset: Train={len(combined_train)}, Val={len(combined_val)}")
    print("=== Dataset Generation Complete ===")


if __name__ == "__main__":
    main()
