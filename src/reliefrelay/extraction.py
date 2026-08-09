import hashlib
import re
from difflib import get_close_matches
from uuid import uuid4

from reliefrelay.domain import Incident, utc_now


INCIDENT_KEYWORDS = {
    "fire": ("fire", "smoke", "burning"),
    "flood": ("flood", "rising water", "flooding"),
    "medical": ("medical", "injured", "injury", "unconscious"),
    "infrastructure": ("collapsed", "power outage", "blocked road"),
}

CRITICAL_TERMS = (
    "trapped",
    "immediately",
    "evacuation",
    "unconscious",
    "life threatening",
    "fire",
)

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

RESPONSE_LOCATIONS = (
    "Riverside Shelter",
    "North Clinic",
    "Harbor School",
)


class EmergencyReportExtractor:
    def __init__(self, known_locations: tuple[str, ...] = ()) -> None:
        self._known_locations = known_locations

    def extract(self, transcript: str) -> Incident:
        normalized = " ".join(transcript.split())
        location = self._extract_location(normalized)
        incident_type = self._extract_incident_type(normalized)

        return Incident(
            id=str(uuid4()),
            fingerprint=self._fingerprint(location, incident_type),
            location=location,
            incident_type=incident_type,
            severity=self._extract_severity(normalized),
            people_affected=self._extract_people_affected(normalized),
            requested_resource=self._extract_requested_resource(normalized),
            transcript=normalized,
            created_at=utc_now(),
        )

    def _extract_location(self, transcript: str) -> str:
        patterns = (
            r"\b(?:at|from) ([A-Z][A-Za-z0-9' -]{2,50}?)(?=\.|,|;| reporting\b)",
            r"^([A-Z][A-Za-z0-9' -]{2,50}?) reporting\b",
        )
        for pattern in patterns:
            match = re.search(pattern, transcript)
            if match:
                location = match.group(1).strip()
                matches = get_close_matches(
                    location,
                    self._known_locations,
                    n=1,
                    cutoff=0.74,
                )
                return matches[0] if matches else location
        return "Unknown location"

    @staticmethod
    def _extract_incident_type(transcript: str) -> str:
        lowered = transcript.lower()
        for incident_type, keywords in INCIDENT_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                return incident_type
        return "other"

    @staticmethod
    def _extract_severity(transcript: str) -> str:
        lowered = transcript.lower()
        if any(term in lowered for term in CRITICAL_TERMS):
            return "critical"
        if any(
            term in lowered
            for term in ("urgent", "condition wors", "conditions wors", "stranded")
        ):
            return "high"
        return "standard"

    @staticmethod
    def _extract_people_affected(transcript: str) -> int | None:
        lowered = transcript.lower()
        digit_match = re.search(r"\b(\d+)\s+(?:people|person|residents?|patients?)\b", lowered)
        if digit_match:
            return int(digit_match.group(1))

        word_pattern = "|".join(NUMBER_WORDS)
        word_match = re.search(
            rf"\b({word_pattern})\s+(?:people|person|residents?|patients?)\b",
            lowered,
        )
        if word_match:
            return NUMBER_WORDS[word_match.group(1)]
        return None

    @staticmethod
    def _extract_requested_resource(transcript: str) -> str | None:
        match = re.search(
            r"\b(?:send|requesting|need) (?:a |an )?"
            r"(rescue team|medical team|ambulance|fire crew|food|water|shelter)\b",
            transcript,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).lower()
        lowered = transcript.lower()
        resources = (
            "rescue team",
            "medical team",
            "ambulance",
            "fire crew",
            "food",
            "water",
            "shelter",
        )
        return next((resource for resource in resources if resource in lowered), None)

    @staticmethod
    def _fingerprint(location: str, incident_type: str) -> str:
        identity = f"{location.casefold()}:{incident_type}"
        return hashlib.sha256(identity.encode()).hexdigest()[:12]
