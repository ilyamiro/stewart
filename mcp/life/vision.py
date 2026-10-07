"""Local vision tools for Unified Life Assistant: OCR, image inspection, and local analysis."""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union

try:
    from PIL import Image, ImageOps, ImageFilter, ExifTags, ImageStat
except ImportError:
    Image = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

logger = logging.getLogger("life.vision")


def _calculate_sharpness(img: Image.Image) -> float:
    """Calculate perceived sharpness using Laplacian filter standard deviation."""
    try:
        gray = img.convert("L")
        laplacian = gray.filter(ImageFilter.FIND_EDGES)
        stat = ImageStat.Stat(laplacian)
        return round(stat.var[0], 2)
    except Exception:
        return 0.0


def _greatest_common_divisor(a: int, b: int) -> int:
    import math
    return math.gcd(a, b)


def inspect_image(image_path: str) -> Dict[str, Any]:
    """Inspects an image file and extracts metadata, dimensions, EXIF, and visual metrics."""
    p = Path(image_path).expanduser().resolve()
    if not p.exists():
        return {"error": f"Image file not found: {image_path}"}
    if not p.is_file():
        return {"error": f"Path is not a regular file: {image_path}"}

    file_size_bytes = p.stat().st_size
    file_size_kb = round(file_size_bytes / 1024, 2)

    try:
        with Image.open(p) as img:
            width, height = img.size
            format_name = img.format or p.suffix.lstrip(".").upper()
            mode = img.mode

            gcd_val = _greatest_common_divisor(width, height)
            aspect_str = f"{width // gcd_val}:{height // gcd_val}" if gcd_val else f"{width}:{height}"
            aspect_ratio_num = round(width / height, 2) if height else 0.0

            stat = ImageStat.Stat(img.convert("L"))
            mean_brightness = round(stat.mean[0], 2)
            contrast_std = round(stat.stddev[0], 2)
            sharpness = _calculate_sharpness(img)

            exif_data = {}
            raw_exif = getattr(img, "_getexif", lambda: None)()
            if raw_exif:
                for tag_id, value in raw_exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if isinstance(value, (bytes, bytearray)):
                        continue
                    if isinstance(value, (int, float, str)):
                        exif_data[tag_name] = value

            return {
                "file_path": str(p),
                "file_name": p.name,
                "file_size_kb": file_size_kb,
                "format": format_name,
                "mode": mode,
                "width": width,
                "height": height,
                "aspect_ratio": aspect_str,
                "aspect_ratio_decimal": aspect_ratio_num,
                "brightness": mean_brightness,
                "contrast": contrast_std,
                "sharpness_score": sharpness,
                "has_exif": len(exif_data) > 0,
                "exif": exif_data if exif_data else None
            }
    except Exception as e:
        return {"error": f"Failed to inspect image: {str(e)}"}


def _preprocess_for_ocr(img: Image.Image, auto_rotate: bool = True) -> Image.Image:
    """Preprocess image to maximize OCR text recognition accuracy."""
    gray = img.convert("L")

    if auto_rotate and pytesseract:
        try:
            osd = pytesseract.image_to_osd(gray, output_type=pytesseract.Output.DICT)
            rotation = osd.get("rotate", 0)
            if rotation in (90, 180, 270):
                gray = gray.rotate(360 - rotation, expand=True)
        except Exception:
            pass

    enhanced = ImageOps.autocontrast(gray, cutoff=2)
    return enhanced


def extract_text(
    image_path: str,
    language: str = "eng",
    preprocess: bool = True,
    detailed: bool = False,
    psm: Optional[int] = None
) -> Dict[str, Any]:
    """Extracts text from an image using Tesseract OCR.
    
    Args:
        image_path: Path to the image file.
        language: Language code(s), e.g. 'eng' (English), 'dan' (Danish), 'rus' (Russian),
                  'ukr' (Ukrainian), 'equ' (Math equations), or combinations like 'eng+dan', 'eng+rus'.
        preprocess: If True, applies grayscale, auto-contrast, and orientation correction.
        detailed: If True, returns structured OCR tokens with coordinates and confidence.
        psm: Page segmentation mode (0..13). Default is 3 (Fully automatic page segmentation).
    """
    p = Path(image_path).expanduser().resolve()
    if not p.exists():
        return {"error": f"Image file not found: {image_path}"}

    if pytesseract is None or Image is None:
        return {"error": "OCR libraries (pytesseract/Pillow) are not installed or available."}

    config_parts = []
    if psm is not None:
        config_parts.append(f"--psm {psm}")
    custom_config = " ".join(config_parts)

    try:
        with Image.open(p) as img:
            proc_img = _preprocess_for_ocr(img) if preprocess else img

            if detailed:
                data = pytesseract.image_to_data(
                    proc_img,
                    lang=language,
                    config=custom_config,
                    output_type=pytesseract.Output.DICT
                )
                items = []
                n_boxes = len(data["text"])
                for i in range(n_boxes):
                    t = data["text"][i].strip()
                    conf = int(data["conf"][i])
                    if t and conf > 0:
                        items.append({
                            "text": t,
                            "confidence": conf,
                            "box": {
                                "left": data["left"][i],
                                "top": data["top"][i],
                                "width": data["width"][i],
                                "height": data["height"][i]
                            },
                            "line_num": data["line_num"][i],
                            "block_num": data["block_num"][i]
                        })
                full_text = pytesseract.image_to_string(proc_img, lang=language, config=custom_config).strip()
                return {
                    "file_path": str(p),
                    "language": language,
                    "word_count": len(items),
                    "text": full_text,
                    "detailed_words": items
                }
            else:
                raw_text = pytesseract.image_to_string(proc_img, lang=language, config=custom_config).strip()
                lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
                return {
                    "file_path": str(p),
                    "language": language,
                    "line_count": len(lines),
                    "text": raw_text
                }

    except Exception as e:
        return {"error": f"OCR extraction failed: {str(e)}"}


def analyze_image(
    image_path: str,
    prompt: Optional[str] = None,
    language: str = "eng+dan+rus"
) -> Dict[str, Any]:
    """Analyzes an image locally: deep inspection, multi-lingual OCR extraction,
    layout detection, and text structure analysis.
    
    Args:
        image_path: Path to the image file.
        prompt: Optional specific question or instruction regarding the image.
        language: Languages to use for OCR extraction (default: 'eng+dan+rus').
    """
    p = Path(image_path).expanduser().resolve()
    if not p.exists():
        return {"error": f"Image file not found: {image_path}"}

    meta = inspect_image(str(p))
    if "error" in meta:
        return meta

    ocr_res = extract_text(str(p), language=language, preprocess=True)
    extracted_text = ocr_res.get("text", "")

    if not extracted_text or any(sym in extracted_text for sym in ["=", "+", "-", "/", "^", "\\"]):
        math_ocr = extract_text(str(p), language="equ", preprocess=True)
        math_text = math_ocr.get("text", "")
        if math_text and len(math_text.strip()) > 5:
            extracted_text += f"\n\n[Detected Math Expressions / Formulas]:\n{math_text}"

    text_length = len(extracted_text.strip())
    word_count = len(extracted_text.split())

    sharpness = meta.get("sharpness_score", 0)
    brightness = meta.get("brightness", 128)
    contrast = meta.get("contrast", 50)

    if text_length > 100:
        content_type = "Document / Worksheet / Textbook Page"
    elif text_length > 20:
        if brightness < 80:
            content_type = "Blackboard / Dark Screen / Notes"
        else:
            content_type = "Handwritten Notes / Diagram with Text / Screen Snippet"
    elif sharpness > 1000 and contrast > 40:
        content_type = "Diagram / Graphical Chart / Illustration"
    else:
        content_type = "Photograph / Scene Image"

    summary_lines = [
        f"**Local Image Analysis** for `{p.name}`:",
        f"- **Content Type**: {content_type}",
        f"- **Dimensions**: {meta.get('width')}x{meta.get('height')} ({meta.get('format')}, Aspect: {meta.get('aspect_ratio')}, Size: {meta.get('file_size_kb')} KB)",
        f"- **Metrics**: Brightness={brightness}/255, Contrast={contrast}, Sharpness={sharpness}",
        f"- **Detected Text Words**: {word_count}"
    ]

    if prompt:
        summary_lines.append(f"- **Focus/Query**: \"{prompt}\"")

    if extracted_text:
        summary_lines.append(f"\n### Extracted Text / Content (OCR):\n```\n{extracted_text}\n```")
    else:
        summary_lines.append("\n*No recognizable printed or handwritten text was detected.*")

    return {
        "status": "success",
        "image_path": str(p),
        "content_type": content_type,
        "metadata": meta,
        "ocr_text": extracted_text,
        "word_count": word_count,
        "analysis": "\n".join(summary_lines)
    }
