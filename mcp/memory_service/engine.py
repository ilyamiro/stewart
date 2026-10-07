import os
import re
import time
import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

TAG_REGEX = re.compile(r'(?:^|\s)#([a-zA-Z0-9_\-]+)')
HEADING_REGEX = re.compile(r'^(#{1,6})\s+(.*)$')
FRONTMATTER_REGEX = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)


class MemoryEngine:
    def __init__(self, memory_dir: Optional[Path] = None):
        if memory_dir is None:
            env_dir = os.environ.get("LIFE_MEMORY_DIR")
            if env_dir:
                self.memory_dir = Path(env_dir).expanduser().resolve()
            else:
                self.memory_dir = Path.home() / "Projects/life/memory"
        else:
            self.memory_dir = Path(memory_dir).expanduser().resolve()

        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.memory_dir / ".memory_index.db"
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files_meta (
                    file_path TEXT PRIMARY KEY,
                    mtime REAL,
                    size INTEGER,
                    chunk_count INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    file_path TEXT,
                    topic TEXT,
                    section TEXT,
                    content TEXT,
                    tags TEXT,
                    line_start INTEGER,
                    line_end INTEGER
                )
            """)
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    id UNINDEXED,
                    topic,
                    section,
                    content,
                    tags,
                    tokenize='porter unicode61'
                )
            """)
            conn.commit()

    def _parse_frontmatter(self, text: str) -> Tuple[Dict[str, Any], str]:
        match = FRONTMATTER_REGEX.match(text)
        if not match:
            return {}, text

        fm_text = match.group(1)
        remaining = text[match.end():]
        meta = {}
        for line in fm_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip().lower()
                v = v.strip()
                if v.startswith("[") and v.endswith("]"):
                    items = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
                    meta[k] = items
                else:
                    meta[k] = v.strip("'\"")
        return meta, remaining

    def _parse_markdown(self, rel_path: str, full_path: Path) -> List[Dict[str, Any]]:
        try:
            raw_text = full_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read {full_path}: {e}")
            return []

        meta, body = self._parse_frontmatter(raw_text)
        default_topic = meta.get("topic") or full_path.stem.replace("_", " ").title()
        fm_tags = meta.get("tags", [])
        if isinstance(fm_tags, str):
            fm_tags = [t.strip() for t in fm_tags.split(",") if t.strip()]

        lines = raw_text.splitlines()
        chunks = []

        current_topic = default_topic
        current_section = "General"
        section_stack: List[Tuple[int, str]] = []
        chunk_lines: List[str] = []
        chunk_line_start = 1
        current_tags = set(fm_tags)

        def flush_chunk(end_line: int):
            nonlocal chunk_lines, chunk_line_start, current_tags
            text_block = "\n".join(chunk_lines).strip()
            if text_block:
                chunk_id = f"{rel_path}:{chunk_line_start}"
                for match in TAG_REGEX.finditer(text_block):
                    current_tags.add(match.group(1).lower())

                chunks.append({
                    "id": chunk_id,
                    "file_path": rel_path,
                    "topic": current_topic,
                    "section": current_section,
                    "content": text_block,
                    "tags": json.dumps(sorted(list(current_tags))),
                    "line_start": chunk_line_start,
                    "line_end": end_line
                })
            chunk_lines = []
            chunk_line_start = end_line + 1
            current_tags = set(fm_tags)

        for line_idx, line in enumerate(lines, start=1):
            heading_match = HEADING_REGEX.match(line)
            if heading_match:
                hashes, title = heading_match.groups()
                level = len(hashes)
                title = title.strip()

                flush_chunk(line_idx - 1)

                if level == 1 and default_topic == full_path.stem.replace("_", " ").title():
                    current_topic = title

                while section_stack and section_stack[-1][0] >= level:
                    section_stack.pop()
                section_stack.append((level, title))
                current_section = " > ".join(s[1] for s in section_stack)
                chunk_line_start = line_idx
                chunk_lines.append(line)
            else:
                chunk_lines.append(line)
                if len("\n".join(chunk_lines)) > 1200 and line.strip() == "":
                    flush_chunk(line_idx)

        flush_chunk(len(lines))
        return chunks

    def sync(self, force: bool = False) -> Dict[str, Any]:
        """Scans markdown files in memory_dir and incrementally syncs SQLite index."""
        if not self.memory_dir.exists():
            self.memory_dir.mkdir(parents=True, exist_ok=True)

        md_files = list(self.memory_dir.glob("**/*.md")) + list(self.memory_dir.glob("**/*.markdown"))
        md_files = [f for f in md_files if not any(part.startswith(".") for part in f.relative_to(self.memory_dir).parts)]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_path, mtime, size FROM files_meta")
            existing_meta = {row["file_path"]: (row["mtime"], row["size"]) for row in cursor.fetchall()}

            current_rel_paths = set()
            files_to_update: List[Tuple[str, Path]] = []

            for f in md_files:
                rel_path = str(f.relative_to(self.memory_dir))
                current_rel_paths.add(rel_path)
                stat = f.stat()
                mtime = stat.st_mtime
                size = stat.st_size

                if force or rel_path not in existing_meta or existing_meta[rel_path] != (mtime, size):
                    files_to_update.append((rel_path, f))

            deleted_files = set(existing_meta.keys()) - current_rel_paths
            for rel_path in deleted_files:
                cursor.execute("DELETE FROM files_meta WHERE file_path = ?", (rel_path,))
                cursor.execute("DELETE FROM chunks WHERE file_path = ?", (rel_path,))
                cursor.execute("DELETE FROM chunks_fts WHERE id LIKE ?", (f"{rel_path}:%",))

            updated_chunks_count = 0
            for rel_path, full_path in files_to_update:
                cursor.execute("DELETE FROM chunks WHERE file_path = ?", (rel_path,))
                cursor.execute("DELETE FROM chunks_fts WHERE id LIKE ?", (f"{rel_path}:%",))

                chunks = self._parse_markdown(rel_path, full_path)
                stat = full_path.stat()
                cursor.execute(
                    "INSERT OR REPLACE INTO files_meta (file_path, mtime, size, chunk_count) VALUES (?, ?, ?, ?)",
                    (rel_path, stat.st_mtime, stat.st_size, len(chunks))
                )

                for chunk in chunks:
                    cursor.execute("""
                        INSERT INTO chunks (id, file_path, topic, section, content, tags, line_start, line_end)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        chunk["id"],
                        chunk["file_path"],
                        chunk["topic"],
                        chunk["section"],
                        chunk["content"],
                        chunk["tags"],
                        chunk["line_start"],
                        chunk["line_end"]
                    ))
                    cursor.execute("""
                        INSERT INTO chunks_fts (id, topic, section, content, tags)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        chunk["id"],
                        chunk["topic"],
                        chunk["section"],
                        chunk["content"],
                        chunk["tags"]
                    ))
                    updated_chunks_count += 1

            conn.commit()
            return {
                "synced_files": len(files_to_update),
                "deleted_files": len(deleted_files),
                "total_active_files": len(current_rel_paths),
                "new_chunks_indexed": updated_chunks_count
            }

    def _prepare_fts_query(self, query: str) -> str:
        tokens = re.findall(r'[a-zA-Z0-9_\u0400-\u04FF]+', query)
        if not tokens:
            return ""
        formatted = " OR ".join([f'"{tok}"*' for tok in tokens])
        return formatted

    def search(self, query: str, limit: int = 5, topic: Optional[str] = None, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fast full-text search over indexed markdown chunks."""
        self.sync()

        fts_query = self._prepare_fts_query(query)
        results = []

        with self._get_connection() as conn:
            cursor = conn.cursor()

            if fts_query:
                try:
                    sql = """
                        SELECT c.id, c.file_path, c.topic, c.section, c.content, c.tags, c.line_start, c.line_end,
                               bm25(chunks_fts) as rank
                        FROM chunks_fts
                        JOIN chunks c ON chunks_fts.id = c.id
                        WHERE chunks_fts MATCH ?
                    """
                    params: List[Any] = [fts_query]

                    if topic:
                        sql += " AND (c.topic LIKE ? OR c.file_path LIKE ?)"
                        params.extend([f"%{topic}%", f"%{topic}%"])
                    if tag:
                        tag_clean = tag.lstrip("#").lower()
                        sql += " AND c.tags LIKE ?"
                        params.append(f'%"{tag_clean}"%')

                    sql += " ORDER BY rank LIMIT ?"
                    params.append(limit)

                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                    for r in rows:
                        tags_list = json.loads(r["tags"]) if r["tags"] else []
                        results.append({
                            "file": r["file_path"],
                            "topic": r["topic"],
                            "section": r["section"],
                            "content": r["content"],
                            "tags": tags_list,
                            "line_start": r["line_start"],
                            "line_end": r["line_end"],
                            "score": round(abs(float(r["rank"])), 3)
                        })
                except Exception as e:
                    logger.warning(f"FTS5 query failed: {e}. Falling back to substring match.")

            if not results:
                sql = "SELECT id, file_path, topic, section, content, tags, line_start, line_end FROM chunks WHERE 1=1"
                params = []
                for word in query.split():
                    sql += " AND (content LIKE ? OR topic LIKE ? OR section LIKE ?)"
                    params.extend([f"%{word}%", f"%{word}%", f"%{word}%"])

                if topic:
                    sql += " AND (topic LIKE ? OR file_path LIKE ?)"
                    params.extend([f"%{topic}%", f"%{topic}%"])
                if tag:
                    tag_clean = tag.lstrip("#").lower()
                    sql += " AND tags LIKE ?"
                    params.append(f'%"{tag_clean}"%')

                sql += " LIMIT ?"
                params.append(limit)

                cursor.execute(sql, params)
                for r in cursor.fetchall():
                    tags_list = json.loads(r["tags"]) if r["tags"] else []
                    results.append({
                        "file": r["file_path"],
                        "topic": r["topic"],
                        "section": r["section"],
                        "content": r["content"],
                        "tags": tags_list,
                        "line_start": r["line_start"],
                        "line_end": r["line_end"],
                        "score": 1.0
                    })

        return results

    def get(self, topic: Optional[str] = None, file_name: Optional[str] = None, section: Optional[str] = None) -> Dict[str, Any]:
        """Fetches full content or a specific section of a topic/file."""
        self.sync()

        target_file: Optional[Path] = None

        if file_name:
            cand = self.memory_dir / file_name
            if cand.exists():
                target_file = cand
            else:
                found = list(self.memory_dir.glob(f"**/{file_name}"))
                if found:
                    target_file = found[0]

        if not target_file and topic:
            cand = self.memory_dir / f"{topic}.md"
            if cand.exists():
                target_file = cand
            else:
                cand_lower = self.memory_dir / f"{topic.lower().replace(' ', '_')}.md"
                if cand_lower.exists():
                    target_file = cand_lower
                else:
                    with self._get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT file_path FROM chunks WHERE topic LIKE ? LIMIT 1", (f"%{topic}%",))
                        row = cursor.fetchone()
                        if row:
                            target_file = self.memory_dir / row["file_path"]

        if not target_file or not target_file.exists():
            return {
                "found": False,
                "error": f"Topic or file '{file_name or topic}' not found in memory database."
            }

        rel_path = str(target_file.relative_to(self.memory_dir))
        full_text = target_file.read_text(encoding="utf-8")

        if section:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT section, content, line_start, line_end, tags
                    FROM chunks
                    WHERE file_path = ? AND section LIKE ?
                    LIMIT 1
                """, (rel_path, f"%{section}%"))
                row = cursor.fetchone()
                if row:
                    tags = json.loads(row["tags"]) if row["tags"] else []
                    return {
                        "found": True,
                        "file": rel_path,
                        "section": row["section"],
                        "content": row["content"],
                        "line_start": row["line_start"],
                        "line_end": row["line_end"],
                        "tags": tags
                    }
                else:
                    return {
                        "found": False,
                        "file": rel_path,
                        "error": f"Section '{section}' not found in {rel_path}."
                    }

        return {
            "found": True,
            "file": rel_path,
            "content": full_text
        }

    def list_topics(self) -> Dict[str, Any]:
        """Provides high-level outline of memory: topics, files, sections, and tags."""
        self.sync()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_path, mtime, size, chunk_count FROM files_meta ORDER BY file_path")
            files_meta = cursor.fetchall()

            files_info = []
            all_tags = set()

            for f in files_meta:
                rel = f["file_path"]
                cursor.execute("SELECT DISTINCT topic, section, tags FROM chunks WHERE file_path = ?", (rel,))
                rows = cursor.fetchall()

                topic_name = rows[0]["topic"] if rows else Path(rel).stem.replace("_", " ").title()
                sections = sorted(list({r["section"] for r in rows if r["section"] != "General"}))
                file_tags = set()
                for r in rows:
                    if r["tags"]:
                        for t in json.loads(r["tags"]):
                            file_tags.add(t)
                            all_tags.add(t)

                mod_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f["mtime"]))
                files_info.append({
                    "file": rel,
                    "topic": topic_name,
                    "sections": sections,
                    "tags": sorted(list(file_tags)),
                    "chunks": f["chunk_count"],
                    "last_modified": mod_time
                })

            return {
                "total_files": len(files_info),
                "total_tags": len(all_tags),
                "all_tags": sorted(list(all_tags)),
                "files": files_info
            }

    def save(self, content: str, topic: str = "notes", section: Optional[str] = None, mode: str = "append", tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Saves or appends notes/facts into a markdown file."""
        clean_topic = topic.strip()
        if not clean_topic.endswith(".md") and not clean_topic.endswith(".markdown"):
            file_name = f"{clean_topic.lower().replace(' ', '_')}.md"
        else:
            file_name = clean_topic

        target_file = self.memory_dir / file_name
        target_file.parent.mkdir(parents=True, exist_ok=True)

        clean_content = content.strip()
        if tags:
            tag_str = " ".join([f"#{t.lstrip('#')}" for t in tags])
            clean_content = f"{clean_content}\n\nTags: {tag_str}"

        if not target_file.exists():
            title = clean_topic.replace(".md", "").replace("_", " ").title()
            doc_lines = [f"# {title}\n"]
            if section:
                doc_lines.append(f"## {section}\n")
            doc_lines.append(clean_content + "\n")
            target_file.write_text("\n".join(doc_lines), encoding="utf-8")
        else:
            current_text = target_file.read_text(encoding="utf-8")
            if section:
                section_header = f"## {section}"
                if section_header in current_text:
                    if mode == "append":
                        parts = current_text.split(section_header, 1)
                        before = parts[0] + section_header
                        after = parts[1]
                        next_heading = re.search(r'\n(#{1,2}\s+)', after)
                        if next_heading:
                            pos = next_heading.start()
                            updated = before + after[:pos].rstrip() + f"\n\n{clean_content}\n" + after[pos:]
                        else:
                            updated = before + after.rstrip() + f"\n\n{clean_content}\n"
                    else:
                        parts = current_text.split(section_header, 1)
                        before = parts[0] + section_header + "\n\n" + clean_content + "\n"
                        after = parts[1]
                        next_heading = re.search(r'\n(#{1,2}\s+)', after)
                        if next_heading:
                            updated = before + after[next_heading.start():]
                        else:
                            updated = before
                    target_file.write_text(updated, encoding="utf-8")
                else:
                    updated = current_text.rstrip() + f"\n\n## {section}\n\n{clean_content}\n"
                    target_file.write_text(updated, encoding="utf-8")
            else:
                if mode == "append":
                    updated = current_text.rstrip() + f"\n\n{clean_content}\n"
                else:
                    title = clean_topic.replace(".md", "").replace("_", " ").title()
                    updated = f"# {title}\n\n{clean_content}\n"
                target_file.write_text(updated, encoding="utf-8")

        self.sync()
        return {
            "status": "success",
            "file": str(target_file.relative_to(self.memory_dir)),
            "topic": clean_topic,
            "section": section,
            "mode": mode
        }

    def delete(self, topic: str, section: Optional[str] = None) -> Dict[str, Any]:
        """Deletes a section or file from memory."""
        res = self.get(topic=topic)
        if not res.get("found"):
            return {"status": "error", "message": f"Topic '{topic}' not found."}

        target_file = self.memory_dir / res["file"]
        if section:
            current_text = target_file.read_text(encoding="utf-8")
            pattern = re.compile(rf'(##\s+{re.escape(section)}\b.*?)(?=\n##|\Z)', re.DOTALL)
            if not pattern.search(current_text):
                return {"status": "error", "message": f"Section '{section}' not found in {res['file']}."}
            updated = pattern.sub("", current_text).strip() + "\n"
            target_file.write_text(updated, encoding="utf-8")
            self.sync()
            return {"status": "success", "message": f"Deleted section '{section}' from {res['file']}."}
        else:
            target_file.unlink()
            self.sync()
            return {"status": "success", "message": f"Deleted file {res['file']}."}


_engine_instance: Optional[MemoryEngine] = None

def get_memory_engine() -> MemoryEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = MemoryEngine()
    return _engine_instance
