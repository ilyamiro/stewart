import os
import re
import json
import logging
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "studieplus" / "ib_resources"
STUDY_MATERIALS_DIR = Path.home() / "Projects" / "life" / "study_materials"

KNOWN_MIRRORS = [
    "https://dl.ibdocs.re",
    "https://repo.ibdocs.re",
    "https://dl.pirateib.su",
    "https://dl.pirateib.sh",
]

SUBJECT_SLUGS = {
    "math": "mathematics-analysis-and-approaches",
    "maths": "mathematics-analysis-and-approaches",
    "math aa": "mathematics-analysis-and-approaches",
    "maths aa": "mathematics-analysis-and-approaches",
    "math aa hl": "mathematics-analysis-and-approaches",
    "maths aa hl": "mathematics-analysis-and-approaches",
    "maths aahl": "mathematics-analysis-and-approaches",
    "math aa sl": "mathematics-analysis-and-approaches",
    "maths aa sl": "mathematics-analysis-and-approaches",
    "math ai": "mathematics-applications-and-interpretation",
    "maths ai": "mathematics-applications-and-interpretation",
    "math ai hl": "mathematics-applications-and-interpretation",
    "math ai sl": "mathematics-applications-and-interpretation",
    "further math": "further-mathematics",

    "physics": "physics",
    "phy": "physics",
    "phy hl": "physics",
    "phy sl": "physics",
    "physics hl": "physics",
    "physics sl": "physics",
    "chemistry": "chemistry",
    "chem": "chemistry",
    "chem hl": "chemistry",
    "chem sl": "chemistry",
    "biology": "biology",
    "bio": "biology",
    "computer science": "computer-science",
    "cs": "computer-science",

    "economics": "economics",
    "eco": "economics",
    "eco hl": "economics",
    "eco sl": "economics",
    "economics hl": "economics",
    "economics sl": "economics",
    "history": "history",
    "his": "history",
    "his hl": "history",
    "his sl": "history",
    "history hl": "history",
    "history sl": "history",
    "business": "business-management",
    "business management": "business-management",
    "psychology": "psychology",
    "psych": "psychology",
    "philosophy": "philosophy",
    "global politics": "global-politics",
    "geography": "geography",

    "english": "english-a-literature",
    "english lit": "english-a-literature",
    "english a lit": "english-a-literature",
    "eng a lit": "english-a-literature",
    "eng lit": "english-a-literature",
    "english a": "english-a-literature",
    "english a literature": "english-a-literature",
    "english lang lit": "english-a-language-and-literature",
    "english a language and literature": "english-a-language-and-literature",
    "english b": "english-b",

    "danish": "danish-a-literature",
    "danish lit": "danish-a-literature",
    "danish a literature": "danish-a-literature",
    "danish a": "danish-a-literature",
    "dan ab": "danish-ab-initio",
    "danish ab": "danish-ab-initio",
    "danish ab initio": "danish-ab-initio",
    "danish-ab-initio": "danish-ab-initio",
    "dan ab sl": "danish-ab-initio",
    "danish b": "danish-b",

    "french": "french-b",
    "spanish": "spanish-b",
    "german": "german-b",
}


def get_working_mirror() -> str:
    """Tests known mirrors and returns the first healthy working mirror."""
    for mirror in KNOWN_MIRRORS:
        try:
            req = urllib.request.Request(mirror, headers={"User-Agent": "Mozilla/5.0"})
            res = urllib.request.urlopen(req, timeout=3)
            if res.status == 200:
                return mirror
        except Exception:
            continue
    return "https://dl.ibdocs.re"


class IBResourcesClient:
    """Client for retrieving and downloading IB past papers and resources."""

    def __init__(self, mirror: Optional[str] = None):
        self.mirror = mirror or get_working_mirror()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        STUDY_MATERIALS_DIR.mkdir(parents=True, exist_ok=True)

    def resolve_subject_slug(self, query: str) -> str:
        q = query.lower().strip()
        if q in SUBJECT_SLUGS:
            return SUBJECT_SLUGS[q]
        for key in sorted(SUBJECT_SLUGS.keys(), key=len, reverse=True):
            if key in q:
                return SUBJECT_SLUGS[key]
        return re.sub(r'[^a-z0-9\-]', '', q.replace(" ", "-"))

    def get_subject_papers(self, subject: str = "math aa") -> List[Dict[str, Any]]:
        """Fetches and caches the past papers list for a given subject."""
        slug = self.resolve_subject_slug(subject)
        cache_file = CACHE_DIR / f"{slug}.json"

        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    if data.get("items"):
                        return data["items"]
            except Exception:
                pass

        url = f"{self.mirror}/past-papers-by-subject/{slug}"
        logger.info(f"Fetching papers list from {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return []

        pattern = r'\{title:\"([^\"]+)\",href:\"([^\"]+)\",year:\"([^\"]+)\",session:\"([^\"]+)\"\}'
        raw_items = re.findall(pattern, html)
        items = []
        for title, href, year, session in raw_items:
            items.append({
                "title": title,
                "href": href,
                "year": year,
                "session": session,
                "subject_slug": slug
            })

        if items:
            with open(cache_file, "w") as f:
                json.dump({"items": items, "subject": slug}, f, indent=2)

        return items

    def search_papers(
        self,
        subject: str = "math aa",
        level: Optional[str] = "HL",
        paper_num: Optional[Union[int, str]] = None,
        year: Optional[Union[int, str]] = None,
        session: Optional[str] = None,
        component: Optional[str] = None,
        query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Filters past papers based on criteria."""
        all_papers = self.get_subject_papers(subject)
        results = []

        for p in all_papers:
            title = p["title"]
            title_lower = title.lower()

            if level and level.upper() not in title:
                continue

            if paper_num:
                p_str = f"paper {paper_num}"
                if p_str not in title_lower and f"p{paper_num}" not in title_lower:
                    continue

            if year and str(year) not in p["year"]:
                continue

            if session and session.lower() not in p["session"].lower():
                continue

            if component:
                comp_lower = component.lower()
                if comp_lower == "markscheme" and "markscheme" not in title_lower:
                    continue
                if comp_lower == "paper" and "markscheme" in title_lower:
                    continue

            if query:
                q_words = query.lower().split()
                if not all(w in title_lower for w in q_words):
                    continue

            results.append(p)

        return results

    def get_direct_download_url(self, href: str) -> Optional[str]:
        """Resolves the direct download URL for a document page."""
        doc_url = f"{self.mirror}{href}"
        req = urllib.request.Request(doc_url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
            match = re.search(r'\"(contentUrl|raw_url)\":\"([^\"]+)\"', html)
            if match:
                url_or_path = match.group(2)
                if url_or_path.startswith("http"):
                    parsed = urllib.parse.urlparse(url_or_path)
                    return f"{self.mirror}{parsed.path}"
                else:
                    return f"{self.mirror}{url_or_path}"
        except Exception as e:
            logger.error(f"Error resolving download URL for {href}: {e}")
        return None

    def download_paper(
        self,
        paper: Dict[str, Any],
        open_after_download: bool = True
    ) -> Dict[str, Any]:
        """Downloads a past paper PDF and optionally opens it with xdg-open."""
        href = paper.get("href")
        if not href:
            return {"success": False, "error": "Missing href"}

        direct_url = self.get_direct_download_url(href)
        if not direct_url:
            return {"success": False, "error": "Could not resolve direct PDF link"}

        slug = paper.get("subject_slug", "general")
        sub_dir = STUDY_MATERIALS_DIR / slug
        sub_dir.mkdir(parents=True, exist_ok=True)

        filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', paper["title"]) + ".pdf"
        dest_path = sub_dir / filename

        if not dest_path.exists() or dest_path.stat().st_size == 0:
            logger.info(f"Downloading {direct_url} to {dest_path}")
            req = urllib.request.Request(direct_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp, open(dest_path, "wb") as out_f:
                out_f.write(resp.read())

        opened = False
        if open_after_download and dest_path.exists():
            try:
                subprocess.Popen(
                    ["xdg-open", str(dest_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                opened = True
            except Exception as e:
                logger.warning(f"Could not open {dest_path} with xdg-open: {e}")

        return {
            "success": True,
            "title": paper["title"],
            "year": paper.get("year"),
            "session": paper.get("session"),
            "file_path": str(dest_path),
            "opened": opened
        }
