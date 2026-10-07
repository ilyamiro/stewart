"""Telegram Message Formatter for Life Assistant.

Adapts raw model markdown output into clean, Telegram-friendly formatting:
- Converts markdown tables into clean readable bullet lists for mobile
- Converts # / ## / ### headers into **BOLD** headings (Telegram doesn't support # headers)
- Converts callouts (> [!NOTE]) into readable emoji callouts
- Strips file:/// local links to clean display text
- Handles message chunking with open/close code fence preservation
"""

import re
from typing import List


def format_for_telegram(text: str) -> str:
    """Format markdown text specifically for Telegram client rendering."""
    if not text:
        return ""

    lines = text.split("\n")
    out_lines: List[str] = []
    in_code_block = False
    table_lines: List[str] = []

    def flush_table(tbl: List[str]) -> List[str]:
        if not tbl:
            return []
        rows = []
        for l in tbl:
            stripped = l.strip()
            if not stripped.startswith("|"):
                continue
            parts = [p.strip() for p in stripped.strip("|").split("|")]
            if all(re.match(r"^[:\s\-]+$", p) for p in parts if p):
                continue
            rows.append(parts)

        if not rows:
            return []

        res = []
        headers = rows[0]
        if len(rows) > 1:
            for r in rows[1:]:
                if len(r) == 2:
                    res.append(f"• **{r[0]}**: {r[1]}")
                elif len(r) == 3:
                    res.append(f"• **{r[0]}**: {r[1]} ({r[2]})")
                elif len(r) > 3:
                    res.append(f"• **{r[0]}**: " + " — ".join(r[1:]))
                elif len(r) == 1:
                    res.append(f"• {r[0]}")
        else:
            res.append("• " + " — ".join(headers))
        return res

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            if table_lines:
                out_lines.extend(flush_table(table_lines))
                table_lines = []
            in_code_block = not in_code_block
            out_lines.append(line)
            continue

        if in_code_block:
            out_lines.append(line)
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(line)
            continue
        elif table_lines:
            out_lines.extend(flush_table(table_lines))
            table_lines = []

        callout_match = re.match(r"^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*)$", stripped, re.IGNORECASE)
        if callout_match:
            kind = callout_match.group(1).upper()
            rest = callout_match.group(2).strip()
            icons = {
                "NOTE": "ℹ️ **Note:**",
                "TIP": "💡 **Tip:**",
                "IMPORTANT": "⚠️ **Important:**",
                "WARNING": "⚠️ **Warning:**",
                "CAUTION": "🛑 **Caution:**"
            }
            prefix = icons.get(kind, "📌")
            out_lines.append(f"{prefix} {rest}" if rest else prefix)
            continue

        header_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if header_match:
            level = len(header_match.group(1))
            header_text = header_match.group(2).strip()
            if level == 1:
                out_lines.append(f"\n**{header_text.upper()}**")
            else:
                out_lines.append(f"\n**{header_text}**")
            continue

        if re.match(r"^\s*[-*_]{3,}\s*$", line):
            out_lines.append("")
            continue

        line = re.sub(r"\[([^\]]+)\]\(file:///[^\)]+\)", r"**\1**", line)

        out_lines.append(line)

    if table_lines:
        out_lines.extend(flush_table(table_lines))

    result = "\n".join(out_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def chunk_telegram_text(text: str, max_length: int = 4000) -> List[str]:
    """Split text into message chunks within Telegram limit, preserving code blocks."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    lines = text.split("\n")
    current_chunk: List[str] = []
    current_len = 0
    in_code = False
    code_lang = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_lang = stripped[3:].strip()
            else:
                in_code = False
                code_lang = ""

        line_len = len(line) + 1

        if current_len + line_len > max_length and current_chunk:
            chunk_str = "\n".join(current_chunk)
            if in_code:
                chunk_str += "\n```"

            chunks.append(chunk_str)

            current_chunk = []
            current_len = 0
            if in_code:
                current_chunk.append(f"```{code_lang}")
                current_len += len(current_chunk[0]) + 1

        current_chunk.append(line)
        current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks
