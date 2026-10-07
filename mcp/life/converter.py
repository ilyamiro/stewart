import sys
import os
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

DOC_EXTENSIONS = {
    ".docx", ".doc", ".odt", ".rtf", ".txt", ".html", ".htm",
    ".xlsx", ".xls", ".ods", ".csv",
    ".pptx", ".ppt", ".odp",
    ".epub"
}

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif", ".ico", ".svg"
}

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".flac", ".wma"
}

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".ts"
}


def convert_document(input_path: Path, output_format: str, output_path: Optional[Path] = None) -> Path:
    """Convert document using LibreOffice (soffice)."""
    target_ext = f".{output_format.lstrip('.')}"
    out_dir = output_path.parent if output_path else input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "soffice",
        "--headless",
        "--convert-to",
        output_format.lstrip("."),
        "--outdir",
        str(out_dir),
        str(input_path)
    ]
    logger.info(f"Running document conversion: {' '.join(cmd)}")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed (exit {res.returncode}): {res.stderr or res.stdout}")

    default_output = out_dir / f"{input_path.stem}{target_ext}"
    if not default_output.exists():
        matches = list(out_dir.glob(f"{input_path.stem}.*"))
        for m in matches:
            if m.suffix.lower() == target_ext.lower():
                default_output = m
                break
        else:
            raise FileNotFoundError(f"Converted file was not created at expected path: {default_output}")

    if output_path and default_output != output_path:
        shutil.move(str(default_output), str(output_path))
        return output_path

    return default_output


def convert_image(input_path: Path, output_format: str, output_path: Optional[Path] = None) -> Path:
    """Convert image using ImageMagick / convert."""
    target_ext = f".{output_format.lstrip('.')}"
    if not output_path:
        output_path = input_path.parent / f"{input_path.stem}{target_ext}"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["convert", str(input_path), str(output_path)]
    logger.info(f"Running image conversion: {' '.join(cmd)}")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"Image conversion failed (exit {res.returncode}): {res.stderr or res.stdout}")

    return output_path


def convert_media(input_path: Path, output_format: str, output_path: Optional[Path] = None) -> Path:
    """Convert audio or video using ffmpeg."""
    target_ext = f".{output_format.lstrip('.')}"
    if not output_path:
        output_path = input_path.parent / f"{input_path.stem}{target_ext}"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y", "-i", str(input_path), str(output_path)]
    logger.info(f"Running media conversion: {' '.join(cmd)}")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"Media conversion failed (exit {res.returncode}): {res.stderr or res.stdout}")

    return output_path


def convert_file(file_path: str, target_format: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    """Auto-detect format and route to appropriate converter."""
    in_path = Path(file_path).expanduser().resolve()
    if not in_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    target_format = target_format.lower().lstrip(".")
    out_target = Path(output_path).expanduser().resolve() if output_path else None

    in_ext = in_path.suffix.lower()

    if target_format == "pdf" or in_ext in DOC_EXTENSIONS:
        res_path = convert_document(in_path, target_format, out_target)
    elif in_ext in IMAGE_EXTENSIONS and f".{target_format}" in IMAGE_EXTENSIONS:
        res_path = convert_image(in_path, target_format, out_target)
    elif (in_ext in AUDIO_EXTENSIONS or in_ext in VIDEO_EXTENSIONS) and (f".{target_format}" in AUDIO_EXTENSIONS or f".{target_format}" in VIDEO_EXTENSIONS):
        res_path = convert_media(in_path, target_format, out_target)
    else:
        try:
            res_path = convert_document(in_path, target_format, out_target)
        except Exception:
            try:
                res_path = convert_media(in_path, target_format, out_target)
            except Exception:
                res_path = convert_image(in_path, target_format, out_target)

    return {
        "status": "success",
        "input_path": str(in_path),
        "output_path": str(res_path),
        "target_format": target_format,
        "size_bytes": res_path.stat().st_size
    }
