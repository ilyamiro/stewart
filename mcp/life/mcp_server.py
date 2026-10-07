import sys
import json
import logging
from typing import Dict, Any

from studieplus.mcp_server import TOOLS as STUDIEPLUS_TOOLS, handle_tool_call as handle_studieplus
from gmail.mcp_server import TOOLS as GMAIL_TOOLS, handle_tool_call as handle_gmail
from telegram.mcp_server import TOOLS as TELEGRAM_TOOLS, handle_tool_call as handle_telegram
from gcalendar.mcp_server import TOOLS as CALENDAR_TOOLS, handle_tool_call as handle_calendar
from github_service.mcp_server import TOOLS as GITHUB_TOOLS, handle_tool_call as handle_github
from gdrive.mcp_server import TOOLS as GDRIVE_TOOLS, handle_tool_call as handle_gdrive
from youtube.mcp_server import TOOLS as YOUTUBE_TOOLS, handle_tool_call as handle_youtube
from gmaps.mcp_server import TOOLS as MAPS_TOOLS, handle_tool_call as handle_maps
from memory_service.mcp_server import TOOLS as MEMORY_TOOLS, handle_tool_call as handle_memory
from streaming.mcp_server import TOOLS as STREAMING_TOOLS, handle_tool_call as handle_streaming

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")

TTS_TOOLS = [
    {
        "name": "tts_synthesize",
        "description": "Synthesizes speech to audio (.ogg/.wav) via Silero TTS. ru=Cyrillic only (transliterate Latin), en=Latin only, 1 line, no emojis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Spoken text (1 line, no emojis)"},
                "language": {"type": "string", "enum": ["auto", "ru", "en"], "default": "auto", "description": "Language: 'ru' or 'en'"},
                "speaker": {"type": "string", "description": "Optional speaker voice"},
                "output_path": {"type": "string", "description": "Output audio file path"},
                "format": {"type": "string", "enum": ["ogg", "wav"], "default": "ogg", "description": "Format: 'ogg' or 'wav'"}
            },
            "required": ["text"]
        }
    }
]

CONVERTER_TOOLS = [
    {
        "name": "convert_file",
        "description": "Converts documents (docx/pdf/txt), images (png/jpg/webp), or audio/video (mp3/wav/ogg/mp4).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Source file path"},
                "target_format": {"type": "string", "description": "Target format/extension (e.g. 'pdf', 'docx', 'png', 'mp3')"},
                "output_path": {"type": "string", "description": "Optional output file path"}
            },
            "required": ["file_path", "target_format"]
        }
    }
]

WEATHER_TOOLS = [
    {
        "name": "weather_get_forecast",
        "description": "Gets current weather and 5-day forecast (temperature, conditions, wind, precipitation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "day_offset": {"type": "integer", "description": "Day offset (0=today, 1=tomorrow, up to 4). If omitted, returns all days."}
            }
        }
    }
]

VISION_TOOLS = [
    {
        "name": "vision_extract_text",
        "description": "Extracts text from images/blackboards/notes via local OCR (supports eng, dan, rus, ukr, equ).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Image file path"},
                "language": {"type": "string", "default": "eng", "description": "OCR languages (e.g. 'eng', 'dan', 'rus', 'equ')"},
                "preprocess": {"type": "boolean", "default": True, "description": "Auto-enhance contrast and orientation"},
                "detailed": {"type": "boolean", "default": False, "description": "Return token bounding boxes and confidence"},
                "psm": {"type": "integer", "description": "Tesseract PSM mode (0..13)"}
            },
            "required": ["image_path"]
        }
    },
    {
        "name": "vision_analyze_image",
        "description": "Analyzes image content: scene description, math/formula solving, diagram inspection, layout categorization.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Image file path"},
                "prompt": {"type": "string", "description": "Specific question or focus for analysis"},
                "language": {"type": "string", "default": "eng+dan+rus", "description": "OCR languages"}
            },
            "required": ["image_path"]
        }
    },
    {
        "name": "vision_inspect_image",
        "description": "Returns image technical metadata: dimensions, aspect ratio, file size, sharpness, brightness, EXIF.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Image file path"}
            },
            "required": ["image_path"]
        }
    }
]

SYSTEM_TOOLS = [
    {
        "name": "system_control",
        "description": "Interacts with this PC across Hyprland, Niri, and Serpantinum desktop shell. Single unified MCP entrypoint for all desktop automation: launching any installed desktop application entry (Discord, Zen Browser, Obsidian, Telegram, Bottles, GIMP, LibreOffice, Mindustry, etc.) or listing apps ('system / apps'), media management (YouTube Music playback & search, playerctl play/pause/next/prev/vol), window control (move, focus, resize, fullscreen, float, close), switching workspaces, taking screenshots (instant full screen capture to file & clipboard, area selection, satty annotation editor, QR scan, recording), toggling Serpantinum UI widgets (launcher, clipboard, music, system dashboard, wallpaper, calendar, network, volume), audio volume & display brightness, locking screen, querying desktop status (active window, workspaces, media track), or dispatching raw compositor/shell IPC commands. Accepts structured arguments or slash-separated IPC calls like '(system / open / terminal)', 'system / open / discord', 'system / apps', 'system / media / youtube_music / lofi beats', 'system / window / move / right', 'system / workspace / 2', 'system / screenshot / full', 'system / shell / toggle / launcher', 'system / volume / raise'. Call this tool to unlock full desktop automation and OS capabilities on this PC.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "IPC command string or slash path, e.g. '(system / open / terminal)', 'system / open / discord', 'system / apps / browser', 'system / open / browser / https://music.youtube.com', 'system / media / youtube_music / lofi beats', 'system / media / play_pause', 'system / window / move / right', 'system / workspace / 2', 'system / screenshot / full', 'system / shell / toggle / launcher', 'system / volume / raise', or 'system / status'."
                },
                "action": {
                    "type": "string",
                    "description": "Action category if not using command string: 'open' (or 'launch' any desktop app entry), 'apps' (list/search installed desktop apps), 'close', 'focus', 'move', 'workspace', 'media', 'screenshot', 'volume', 'brightness', 'lock', 'shell', 'status', or 'raw'."
                },
                "target": {
                    "type": "string",
                    "description": "Action target: desktop app name or ID (e.g. 'terminal', 'discord', 'zen', 'obsidian', 'bottles', 'calc', 'telegram', 'com.discordapp.Discord'), search query for apps ('browser', 'game'), direction ('left', 'right', 'up', 'down'), workspace number, shell widget ('launcher', 'clipboard', 'music', 'system', 'wallpaper', 'calendar', 'network', 'volume'), media action ('play', 'pause', 'play_pause', 'next', 'previous'), or screenshot mode ('full', 'area', 'edit', 'record', 'scan_qr')."
                },
                "args": {
                    "type": "string",
                    "description": "Optional parameters or arguments, e.g. URL for browser, search query for YouTube Music, file path or extra parameters for desktop apps, workspace number, delta for volume/brightness, or raw command."
                }
            }
        }
    }
]

ALL_TOOLS = STUDIEPLUS_TOOLS + GMAIL_TOOLS + TELEGRAM_TOOLS + CALENDAR_TOOLS + GITHUB_TOOLS + GDRIVE_TOOLS + YOUTUBE_TOOLS + MAPS_TOOLS + MEMORY_TOOLS + TTS_TOOLS + CONVERTER_TOOLS + WEATHER_TOOLS + VISION_TOOLS + SYSTEM_TOOLS + STREAMING_TOOLS



def handle_tts(name: str, args: Dict[str, Any]) -> str:
    text = args.get("text", "")
    if not text:
        return json.dumps({"error": "text is required"})
    lang = args.get("language", "auto")
    speaker = args.get("speaker")
    output_format = args.get("format", "ogg")
    custom_path = args.get("output_path")

    try:
        from telegram_bridge.tts import get_synthesizer
        import shutil
        from pathlib import Path
        synth = get_synthesizer()
        file_path, used_lang = synth.synthesize(text, lang=lang, speaker=speaker, output_format=output_format)
        if custom_path:
            p = Path(custom_path).expanduser().resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(file_path, str(p))
            file_path = str(p)
        return json.dumps({
            "status": "success",
            "file_path": file_path,
            "language": used_lang,
            "format": output_format
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to synthesize audio: {str(e)}"})


def handle_converter(name: str, args: Dict[str, Any]) -> str:
    from life.converter import convert_file
    file_path = args.get("file_path")
    target_format = args.get("target_format")
    output_path = args.get("output_path")
    if not file_path or not target_format:
        return json.dumps({"error": "file_path and target_format are required"})
    try:
        res = convert_file(file_path, target_format, output_path)
        return json.dumps(res)
    except Exception as e:
        return json.dumps({"error": f"Conversion failed: {str(e)}"})


def handle_weather(name: str, args: Dict[str, Any]) -> str:
    import subprocess
    day_offset = args.get("day_offset")
    try:
        res = subprocess.run(
            ["serpantinum", "weather", "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        if res.returncode != 0:
            return json.dumps({"error": f"Weather fetch failed: {res.stderr or res.stdout}"})
        data = json.loads(res.stdout)
        if day_offset is not None:
            forecasts = data.get("forecast", [])
            if 0 <= day_offset < len(forecasts):
                return json.dumps({
                    "unit": data.get("unit"),
                    "unit_sym": data.get("unit_sym"),
                    "current_temp": data.get("current_temp"),
                    "day_forecast": forecasts[day_offset]
                })
            else:
                return json.dumps({"error": f"day_offset {day_offset} out of range (0..{len(forecasts)-1})"})
        return json.dumps(data)
    except Exception as e:
        return json.dumps({"error": f"Failed to get weather forecast: {str(e)}"})


def handle_vision(name: str, args: Dict[str, Any]) -> str:
    from life.vision import inspect_image, extract_text, analyze_image
    try:
        if name == "vision_inspect_image":
            image_path = args.get("image_path")
            if not image_path:
                return json.dumps({"error": "image_path is required"})
            return json.dumps(inspect_image(image_path))
        elif name == "vision_extract_text":
            image_path = args.get("image_path")
            if not image_path:
                return json.dumps({"error": "image_path is required"})
            lang = args.get("language", "eng")
            prep = args.get("preprocess", True)
            detailed = args.get("detailed", False)
            psm = args.get("psm")
            return json.dumps(extract_text(image_path, language=lang, preprocess=prep, detailed=detailed, psm=psm))
        elif name == "vision_analyze_image":
            image_path = args.get("image_path")
            if not image_path:
                return json.dumps({"error": "image_path is required"})
            prompt = args.get("prompt")
            lang = args.get("language", "eng+dan+rus")
            return json.dumps(analyze_image(image_path, prompt=prompt, language=lang))
        else:
            return json.dumps({"error": f"Unknown vision tool: {name}"})
    except Exception as e:
        return json.dumps({"error": f"Vision tool execution failed: {str(e)}"})


def handle_tool_call(name: str, args: Dict[str, Any]) -> str:
    if name.startswith("studieplus_") or name.startswith("study_"):
        return handle_studieplus(name, args)
    elif name.startswith("gmail_"):
        return handle_gmail(name, args)
    elif name.startswith("telegram_"):
        return handle_telegram(name, args)
    elif name.startswith("calendar_"):
        return handle_calendar(name, args)
    elif name.startswith("github_"):
        return handle_github(name, args)
    elif name.startswith("gdrive_"):
        return handle_gdrive(name, args)
    elif name.startswith("youtube_"):
        return handle_youtube(name, args)
    elif name.startswith("maps_"):
        return handle_maps(name, args)
    elif name.startswith("memory_"):
        return handle_memory(name, args)
    elif name.startswith("tts_"):
        return handle_tts(name, args)
    elif name == "convert_file":
        return handle_converter(name, args)
    elif name.startswith("weather_"):
        return handle_weather(name, args)
    elif name.startswith("vision_"):
        return handle_vision(name, args)
    elif name.startswith("streaming_"):
        return handle_streaming(name, args)
    elif name in ("system_control", "system_ipc"):
        from life.system_control import execute_system_control
        res = execute_system_control(
            action=args.get("action"),
            target=args.get("target"),
            args=args.get("args"),
            command=args.get("command")
        )
        return json.dumps(res)
    else:
        return json.dumps({"error": f"Unknown tool: {name}"})



def main():
    logging.info(f"Starting Unified Life MCP Server with {len(ALL_TOOLS)} tools...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            logging.error(f"Malformed JSON: {e}")
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if req_id is None:
            if method == "notifications/initialized":
                logging.info("Client initialized notification received.")
            continue

        resp = {"jsonrpc": "2.0", "id": req_id}

        try:
            if method == "initialize":
                resp["result"] = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "life-mcp",
                        "version": "1.2.0"
                    }
                }
            elif method == "tools/list":
                resp["result"] = {"tools": ALL_TOOLS}
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                logging.info(f"Calling tool {tool_name} with args: {tool_args}")
                text_result = handle_tool_call(tool_name, tool_args)
                resp["result"] = {
                    "content": [
                        {
                            "type": "text",
                            "text": text_result
                        }
                    ]
                }
            elif method == "ping":
                resp["result"] = {}
            else:
                resp["error"] = {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
        except Exception as e:
            logging.exception(f"Error handling method {method}: {e}")
            resp["error"] = {
                "code": -32603,
                "message": str(e)
            }

        response_json = json.dumps(resp)
        sys.stdout.write(response_json + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
