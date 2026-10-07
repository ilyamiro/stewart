import re
import logging
from typing import List, Dict, Any, Optional

from .gateway import StudiePlusGateway
from .ib_resources import IBResourcesClient

logger = logging.getLogger(__name__)

ALL_SUBJECT_TOPICS: Dict[str, Dict[str, List[str]]] = {
    "math": {
        "Vectors (Lines & Planes)": [
            "vector", "vectors", "plane", "distance from a point", "point to a line", "section 9.1", "p. 381", "p. 416", "p. 430"
        ],
        "Sequences & Series": [
            "arithmetic", "geometric", "sequence", "series", "sigma", "sum to infinity", "section 3.1", "section 3.2", "section 3.3", "section 3.4", "p. 108", "p. 112", "p. 115", "p. 122"
        ],
        "Permutations, Combinations & Counting": [
            "counting", "permutation", "combination", "factorial", "arrangements", "selection", "p. 142", "p. 145", "exercise 3.5"
        ],
        "The Binomial Theorem": [
            "binomial", "theorem", "expansion", "coefficients", "pascal", "section 3.5", "p. 135"
        ],
        "Proof & Mathematical Induction": [
            "induction", "proof", "divisibility", "base step", "inductive step"
        ],
        "Functions & Equations": [
            "function", "domain", "range", "inverse", "composite", "quadratic", "polynomial", "transformation"
        ],
        "Trigonometry": [
            "trig", "sin", "cos", "tan", "radians", "unit circle", "identities", "double angle"
        ],
        "Calculus": [
            "derivative", "differentiation", "integral", "integration", "antiderivative", "chain rule", "product rule", "quotient rule", "tangent", "normal", "optimization"
        ]
    },
    "physics": {
        "Electromagnetic Induction & Fields": [
            "electromagnetic", "induction", "lenz", "faraday", "magnetic", "flux", "ahl topic", "emf", "generator", "transformer"
        ],
        "Electricity & Circuits": [
            "circuit", "current", "voltage", "resistance", "kirchhoff", "potential", "power", "ohm"
        ],
        "Mechanics": [
            "kinematics", "force", "newton", "momentum", "energy", "work", "power", "friction", "projectile"
        ],
        "Thermal Physics": [
            "thermal", "heat", "temperature", "specific heat", "gas laws", "ideal gas", "internal energy"
        ],
        "Waves & Oscillations": [
            "wave", "oscillation", "simple harmonic", "interference", "diffraction", "doppler", "standing wave", "sound"
        ],
        "Atomic, Nuclear & Quantum Physics": [
            "nuclear", "decay", "radioactivity", "fission", "fusion", "half-life", "photon", "quantum", "rutherford", "energy level"
        ]
    },
    "economics": {
        "The Global Economy & Exchange Rates": [
            "exchange rate", "fixed exchange", "floating", "depreciation", "appreciation", "currency", "p. 504", "p. 506", "forex", "central bank intervention"
        ],
        "International Trade & Protectionism": [
            "tariff", "quota", "subsidy", "trade", "free trade", "wto", "protectionism", "comparative advantage", "current account"
        ],
        "Macroeconomics": [
            "gdp", "inflation", "unemployment", "monetary policy", "fiscal policy", "central bank", "interest rate", "aggregate demand", "aggregate supply"
        ],
        "Microeconomics & Market Failure": [
            "demand", "supply", "elasticity", "ped", "pes", "tax", "externality", "monopoly", "public goods", "market failure", "allocative efficiency"
        ]
    },
    "history": {
        "Causes and Effects of 20th Century Wars (WW1 & WW2)": [
            "ww1", "ww2", "world war", "treaty of versailles", "causes of war", "p2 compare", "combatants", "total war", "alliance system"
        ],
        "Authoritarian States & The Interwar Period": [
            "nazi", "hitler", "germany in the 1930s", "authoritarian", "propaganda", "weimar", "stalin", "mussolini", "frihedens fald", "aros", "totalitarian"
        ],
        "The Cold War": [
            "cold war", "containment", "truman", "korea", "vietnam", "berlin wall", "detente", "cuban missile crisis", "nato", "warsaw pact"
        ],
        "Rights & Protest": [
            "apartheid", "civil rights", "mandela", "mlk", "segregation", "protest", "us civil rights"
        ]
    },
    "english": {
        "Literary Analysis & Drama (The Tempest)": [
            "tempest", "shakespeare", "prospero", "caliban", "miranda", "themes", "drama", "motif", "character", "colonialism", "power"
        ],
        "Paper 1 Guided Analysis": [
            "paper 1", "guided analysis", "prose", "poetry", "stylistic features", "tone", "metaphor", "imagery", "structure"
        ],
        "Paper 2 Comparative Essay": [
            "paper 2", "p2", "comparative", "compare and contrast", "two works", "thesis", "literary conventions"
        ]
    },
    "danish": {
        "Reading Comprehension & Vocabulary": [
            "læs", "opgave", "puls 2", "vocabulary", "ordforråd", "tekst", "forståelse", "opgave 11"
        ],
        "Danish Culture & Song Analysis": [
            "danmark er jeg født", "hc andersen", "sang", "kultur", "danmark", "h.c. andersen"
        ],
        "Grammar & Sentence Construction": [
            "grammatik", "bøjning", "ordstilling", "verber", "substantiver", "adjektiver"
        ]
    }
}

SUBJECT_CATEGORY_MAP = {
    "math": ("Math", "math"),
    "maths": ("Math", "math"),
    "maths aa hl": ("Math", "math"),
    "math aa hl": ("Math", "math"),
    "math aa": ("Math", "math"),
    "physics": ("Phy", "physics"),
    "phy": ("Phy", "physics"),
    "phy hl": ("Phy", "physics"),
    "phy sl": ("Phy", "physics"),
    "economics": ("Eco", "economics"),
    "eco": ("Eco", "economics"),
    "eco hl": ("Eco", "economics"),
    "eco sl": ("Eco", "economics"),
    "history": ("His", "history"),
    "his": ("His", "history"),
    "his hl": ("His", "history"),
    "english": ("Eng", "english"),
    "english a lit": ("Eng", "english"),
    "eng a lit": ("Eng", "english"),
    "eng lit": ("Eng", "english"),
    "danish": ("Dan", "danish"),
    "dan ab": ("Dan", "danish"),
    "dan ab sl": ("Dan", "danish"),
    "tok": ("TOK", "tok"),
    "theory of knowledge": ("TOK", "tok")
}


class StudyAssistant:
    """Coordinates study materials, syllabus topic extraction from class history,

    and past paper / questionbank retrieval across all IB subjects.
    """

    def __init__(self, gateway: Optional[StudiePlusGateway] = None, ib_client: Optional[IBResourcesClient] = None):
        self.gateway = gateway or StudiePlusGateway()
        self.ib_client = ib_client or IBResourcesClient()

    def _resolve_subject_category(self, subject: str):
        sub_lower = subject.lower().strip()
        if sub_lower in SUBJECT_CATEGORY_MAP:
            return SUBJECT_CATEGORY_MAP[sub_lower]
        for k, v in SUBJECT_CATEGORY_MAP.items():
            if k in sub_lower:
                return v
        return (subject, sub_lower)

    def get_subject_topics(
        self,
        subject: str = "Maths AA HL",
        from_date: str = "2026-08-10",
        to_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyzes historical lessons and homework for ANY subject to extract covered topics."""
        timetable_query, category = self._resolve_subject_category(subject)
        lessons = self.gateway.get_subject_history(subject=timetable_query, from_date=from_date, to_date=to_date)

        if len(lessons) < 2:
            logger.info(f"Few lessons found for {timetable_query}, syncing history from Studie+...")
            self.gateway.sync_history(from_date=from_date, to_date=to_date)
            lessons = self.gateway.get_subject_history(subject=timetable_query, from_date=from_date, to_date=to_date)

        topic_mapping = ALL_SUBJECT_TOPICS.get(category, {})
        detected_topics: Dict[str, List[Dict[str, Any]]] = {}
        all_homework_entries = []

        for lesson in lessons:
            hw = lesson.get("homework") or ""
            note = lesson.get("note") or ""
            text = f"{hw} {note}".strip()
            if not text:
                continue

            entry = {
                "date": lesson.get("date"),
                "day": lesson.get("day_name"),
                "subject": lesson.get("subject"),
                "homework": hw,
                "note": note
            }
            all_homework_entries.append(entry)

            text_lower = text.lower()
            matched = False
            for topic_name, keywords in topic_mapping.items():
                if any(kw in text_lower for kw in keywords):
                    if topic_name not in detected_topics:
                        detected_topics[topic_name] = []
                    detected_topics[topic_name].append(entry)
                    matched = True

            if not matched and len(text) > 5:
                gen_name = "General Curriculum Focus"
                if gen_name not in detected_topics:
                    detected_topics[gen_name] = []
                detected_topics[gen_name].append(entry)

        return {
            "subject": subject,
            "category": category,
            "timetable_query": timetable_query,
            "from_date": from_date,
            "to_date": to_date,
            "total_lessons_recorded": len(lessons),
            "homework_entries": all_homework_entries,
            "covered_topics": detected_topics
        }

    def prepare_test(
        self,
        subject: str = "Maths AA HL",
        test_date: str = "2026-10-27",
        from_date: str = "2026-08-10",
        auto_download_papers: bool = True,
        open_after_download: bool = True
    ) -> Dict[str, Any]:
        """Gathers covered topics up to test date for ANY subject,

        and fetches matching past papers and markschemes for revision.
        """
        topics_info = self.get_subject_topics(subject=subject, from_date=from_date, to_date=test_date)
        covered_topics = list(topics_info["covered_topics"].keys())

        sub_upper = subject.upper()
        level = "SL" if "SL" in sub_upper and "HL" not in sub_upper else "HL"

        recent_papers = self.ib_client.search_papers(
            subject=subject,
            level=level,
            year="2025",
            component="paper"
        )
        if not recent_papers:
            recent_papers = self.ib_client.search_papers(
                subject=subject,
                level=level,
                year="2024",
                component="paper"
            )
        if not recent_papers:
            recent_papers = self.ib_client.search_papers(
                subject=subject,
                level=None,
                year="2024",
                component="paper"
            )

        downloaded_files = []
        if auto_download_papers and recent_papers:
            p1 = [p for p in recent_papers if "paper 1" in p["title"].lower() or "p1" in p["title"].lower()]
            p2 = [p for p in recent_papers if "paper 2" in p["title"].lower() or "p2" in p["title"].lower()]

            to_download = []
            if p1:
                to_download.append(p1[0])
            if p2:
                to_download.append(p2[0])
            if not to_download:
                to_download.append(recent_papers[0])

            for p in to_download:
                res = self.ib_client.download_paper(p, open_after_download=open_after_download)
                downloaded_files.append(res)
                ms_results = self.ib_client.search_papers(
                    subject=subject,
                    level=level,
                    year=p.get("year"),
                    session=p.get("session"),
                    component="markscheme"
                )
                if ms_results:
                    ms_res = self.ib_client.download_paper(ms_results[0], open_after_download=False)
                    downloaded_files.append(ms_res)

        return {
            "test_date": test_date,
            "subject": subject,
            "level": level,
            "covered_topics": covered_topics,
            "topic_details": topics_info["covered_topics"],
            "homework_timeline": topics_info["homework_entries"][-8:],
            "downloaded_materials": downloaded_files
        }
