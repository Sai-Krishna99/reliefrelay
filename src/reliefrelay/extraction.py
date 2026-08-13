import hashlib
import re
from difflib import get_close_matches
from uuid import uuid4

from reliefrelay.domain import ExtractionAssessment, Incident, utc_now


INCIDENT_KEYWORDS = {
    "fire": ("fire", "smoke", "burning"),
    "flood": ("flood", "rising water", "flooding"),
    "medical": ("medical", "injured", "injury", "unconscious"),
    "infrastructure": ("collapsed", "power outage", "blocked road"),
}

CRITICAL_TERMS = (
    "trapped",
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
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
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
        return self.extract_with_assessment(transcript).incident

    def extract_with_assessment(self, transcript: str) -> ExtractionAssessment:
        normalized = " ".join(transcript.split())
        location, location_confidence = self._extract_location(normalized)
        incident_type = self._extract_incident_type(normalized)
        people_affected = self._extract_people_affected(normalized)
        requested_resource = self._extract_requested_resource(normalized)
        warnings: list[str] = []
        field_scores = [location_confidence]

        if incident_type == "other":
            warnings.append("Incident type could not be determined")
            field_scores.append(0.35)
        else:
            field_scores.append(0.92)
        if location == "Unknown location":
            warnings.append("Location requires operator confirmation")
        if people_affected is None:
            warnings.append("Number of people affected was not stated")
        if requested_resource is None:
            warnings.append("Requested resource was not stated")

        severity = self._extract_severity(normalized)
        confidence = round(sum(field_scores) / len(field_scores), 2)
        review_required = True
        fingerprint = self._fingerprint(location, incident_type, normalized)

        incident = Incident(
            id=str(uuid4()),
            fingerprint=fingerprint,
            location=location,
            incident_type=incident_type,
            severity=severity,
            people_affected=people_affected,
            requested_resource=requested_resource,
            transcript=normalized,
            created_at=utc_now(),
            extraction_confidence=confidence,
            review_required=review_required,
            warnings=tuple(warnings),
        )
        return ExtractionAssessment(
            incident=incident,
            confidence=confidence,
            review_required=review_required,
            warnings=tuple(warnings),
        )

    def _extract_location(self, transcript: str) -> tuple[str, float]:
        lowered = transcript.casefold()
        for known_location in self._known_locations:
            if known_location.casefold() in lowered:
                return known_location, 0.98

        patterns = (
            r"\b(?:at|from)\s+([A-Za-z0-9][A-Za-z0-9' -]{1,70}?)(?=\.|,|;|\s+reporting\b|$)",
            r"^([A-Za-z0-9][A-Za-z0-9' -]{1,70}?)\s+reporting\b",
        )
        for pattern in patterns:
            match = re.search(pattern, transcript, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                matches = get_close_matches(
                    location,
                    self._known_locations,
                    n=1,
                    cutoff=0.74,
                )
                return (matches[0], 0.86) if matches else (location, 0.72)
        return "Unknown location", 0.2

    @staticmethod
    def _is_negated(text: str, start: int) -> bool:
        prefix = text[max(0, start - 45):start]
        return bool(
            re.search(
                r"\b(?:no|not|without|false alarm|clear of|contained)\b(?:\W+\w+){0,3}\W*$",
                prefix,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _extract_incident_type(transcript: str) -> str:
        lowered = transcript.lower()
        for incident_type, keywords in INCIDENT_KEYWORDS.items():
            for keyword in keywords:
                for match in re.finditer(rf"\b{re.escape(keyword)}\b", lowered):
                    if not EmergencyReportExtractor._is_negated(lowered, match.start()):
                        return incident_type
        return "other"

    @staticmethod
    def _extract_severity(transcript: str) -> str:
        lowered = transcript.lower()
        for term in CRITICAL_TERMS:
            for match in re.finditer(rf"\b{re.escape(term)}\b", lowered):
                if not EmergencyReportExtractor._is_negated(lowered, match.start()):
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

        word_pattern = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
        word_match = re.search(
            rf"\b((?:(?:{word_pattern})[ -]?)+)\s+(?:people|person|residents?|patients?)\b",
            lowered,
        )
        if word_match:
            words = re.findall(r"[a-z]+", word_match.group(1))
            total = 0
            current = 0
            for word in words:
                value = NUMBER_WORDS[word]
                if value == 100:
                    current = max(1, current) * value
                else:
                    current += value
            total += current
            return total
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
        unambiguous_resources = (
            "rescue team",
            "medical team",
            "ambulance",
            "fire crew",
        )
        return next(
            (resource for resource in unambiguous_resources if resource in lowered),
            None,
        )

    @staticmethod
    def _fingerprint(
        location: str,
        incident_type: str,
        transcript: str = "",
    ) -> str:
        identity = f"{location.casefold()}:{incident_type}"
        if location == "Unknown location" or incident_type == "other":
            identity = f"{identity}:{transcript.casefold()}"
        return hashlib.sha256(identity.encode()).hexdigest()[:12]
