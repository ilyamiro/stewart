"""Teacher initials, official roles, and subjects directory for Aarhus Gymnasium (Tilst IB).
Verified against aarhusgym.dk staff registry and Studie+ user directory.
"""

from typing import Optional, Dict, Any, List

TEACHER_DETAILS: Dict[str, Dict[str, Any]] = {
    "dtg": {
        "name": "Daniel Thomas Goodwin",
        "display_name": "Danny Goodwin",
        "roles": ["IB CAS Coordinator", "IB Student Counsellor"],
        "subjects": ["English", "Danish", "History"],
    },
    "jwl": {
        "name": "Jørgen Winther Lassen",
        "display_name": "Jørgen Winther Lassen",
        "roles": ["Lektor"],
        "subjects": ["Mathematics", "History"],
    },
    "kims": {
        "name": "Kim Sønderborg",
        "display_name": "Kim Sønderborg",
        "roles": ["Lektor"],
        "subjects": ["History HL", "English", "TOK"],
    },
    "kkn": {
        "name": "Kristen Kirk Nygaard",
        "display_name": "Kristen Kirk Nygaard",
        "roles": ["Lektor"],
        "subjects": ["Economics SL/HL", "Samfundsfag (Social Studies)", "Danish"],
    },
    "lela": {
        "name": "Lene Birk Larsen",
        "display_name": "Lene Birk Larsen",
        "roles": ["Reading Counsellor (Læsevejleder)", "Lektor"],
        "subjects": ["Danish ab initio SL", "Danish", "Religion"],
    },
    "majm": {
        "name": "Maja Mailund",
        "display_name": "Maja Mailund",
        "roles": ["Head of Education (Uddannelsesleder)", "Lektor"],
        "subjects": ["Mathematics", "French", "Samfundsfag"],
    },
    "mas": {
        "name": "Malene Sørensen",
        "display_name": "Malene Sørensen",
        "roles": ["IB Coordinator", "Lektor"],
        "subjects": ["History", "Religion", "Cohort"],
    },
    "mfli": {
        "name": "Maria Friis Lindinger",
        "display_name": "Maria Friis Lindinger",
        "roles": ["Pre-IB Coordinator", "Head of IB Admissions", "CAS Coordinator"],
        "subjects": ["English", "Pre-IB English"],
    },
    "mhah": {
        "name": "Johannes Min-Ho Ahn",
        "display_name": "Min-Ho Ahn",
        "roles": ["EE Supervisor", "Lektor"],
        "subjects": ["Mathematics AA HL/SL", "Informatik"],
    },
    "mif": {
        "name": "Michael Fæster",
        "display_name": "Michael Fæster",
        "roles": ["Student Counsellor (Studievejleder)", "Ambassador Guide", "Lektor"],
        "subjects": ["History", "Sports (Idræt)"],
    },
    "pwe": {
        "name": "Paul Carter Welch",
        "display_name": "Paul Welch",
        "roles": ["IB University Counsellor", "Lektor"],
        "subjects": ["English A Literature SL/HL", "TOK"],
    },
    "shmi": {
        "name": "Sheba Sutharshini Michaelpillai",
        "display_name": "Sheba Sutharshini Michaelpillai",
        "roles": ["Lektor"],
        "subjects": ["Mathematics", "Chemistry"],
    },
    "vlu": {
        "name": "Van Luong",
        "display_name": "Van Luong",
        "roles": ["Lektor"],
        "subjects": ["Mathematics"],
    },
    "ym": {
        "name": "Yevhen Miroshnychenko",
        "display_name": "Yevhen Miroshnychenko",
        "roles": ["Lektor"],
        "subjects": ["Physics HL/SL", "Mathematics"],
    },
}

TEACHER_DEFINITIONS: Dict[str, str] = {
    initial: details["name"] for initial, details in TEACHER_DETAILS.items()
}

TEACHER_NAMES_TO_INITIALS: Dict[str, str] = {}
for initial, details in TEACHER_DETAILS.items():
    TEACHER_NAMES_TO_INITIALS[details["name"].lower()] = initial
    if "display_name" in details:
        TEACHER_NAMES_TO_INITIALS[details["display_name"].lower()] = initial


def resolve_teacher_name(initials: Optional[str]) -> Optional[str]:
    """Resolves teacher initial(s) such as 'mhah' or combined 'kims-pwe' into full names."""
    if not initials:
        return None

    if any(sep in initials for sep in ("-", "/", " ")):
        parts = [p.strip() for p in initials.replace("/", "-").replace(" ", "-").split("-") if p.strip()]
        resolved_parts = [TEACHER_DEFINITIONS.get(p.lower(), p) for p in parts]
        return " / ".join(resolved_parts)

    return TEACHER_DEFINITIONS.get(initials.lower(), initials)


def get_teacher_info(initials: Optional[str]) -> Optional[Dict[str, Any]]:
    """Returns the full dictionary of roles and subjects for a given teacher initial."""
    if not initials:
        return None
    return TEACHER_DETAILS.get(initials.lower().strip())


def get_initials_for_teacher(name: Optional[str]) -> Optional[str]:
    """Returns the initials for a given teacher's full name, if known."""
    if not name:
        return None
    clean = name.strip().lower()
    if clean in TEACHER_NAMES_TO_INITIALS:
        return TEACHER_NAMES_TO_INITIALS[clean]
    for full_name, initial in TEACHER_NAMES_TO_INITIALS.items():
        if full_name in clean or clean in full_name:
            return initial
    return None
