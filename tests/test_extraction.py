from reliefrelay.extraction import EmergencyReportExtractor, RESPONSE_LOCATIONS


def test_extracts_structured_incident_from_field_report() -> None:
    extractor = EmergencyReportExtractor()

    incident = extractor.extract(
        "Unit 12 reporting from Riverside Shelter. "
        "We have rising flood water and twelve people need evacuation. "
        "Send a rescue team immediately."
    )

    assert incident.location == "Riverside Shelter"
    assert incident.incident_type == "flood"
    assert incident.severity == "critical"
    assert incident.people_affected == 12
    assert incident.requested_resource == "rescue team"


def test_stable_fingerprint_groups_related_reports() -> None:
    extractor = EmergencyReportExtractor()

    first = extractor.extract(
        "Flooding at Riverside Shelter. Six people need evacuation."
    )
    second = extractor.extract(
        "Riverside Shelter reporting flood water. Send rescue support."
    )

    assert first.fingerprint == second.fingerprint


def test_unknown_fields_are_explicit() -> None:
    extractor = EmergencyReportExtractor()

    incident = extractor.extract("Requesting assistance. Conditions worsening.")

    assert incident.location == "Unknown location"
    assert incident.incident_type == "other"
    assert incident.people_affected is None


def test_known_location_resolver_corrects_degraded_asr_name() -> None:
    extractor = EmergencyReportExtractor(known_locations=RESPONSE_LOCATIONS)

    incident = extractor.extract(
        "Medic 4 reporting from North Carolina. Fire in the east wing. "
        "Two patients trapped. Send a rescue team in New York."
    )

    assert incident.location == "North Clinic"
    assert incident.requested_resource == "rescue team"


def test_degraded_urgency_and_resource_language_remains_actionable() -> None:
    extractor = EmergencyReportExtractor(known_locations=RESPONSE_LOCATIONS)

    incident = extractor.extract(
        "Team 7 reporting from Harbor School. Three people injured in "
        "conditions worse than me. And a medical team."
    )

    assert incident.severity == "high"
    assert incident.requested_resource == "medical team"


def test_negated_fire_is_not_routed_as_critical_fire() -> None:
    extractor = EmergencyReportExtractor(known_locations=RESPONSE_LOCATIONS)

    incident = extractor.extract("No fire at North Clinic. Situation is safe.")

    assert incident.incident_type == "other"
    assert incident.severity == "standard"


def test_compound_number_words_are_counted_as_one_quantity() -> None:
    extractor = EmergencyReportExtractor(known_locations=RESPONSE_LOCATIONS)

    incident = extractor.extract("Twenty five people injured at Harbor School.")

    assert incident.people_affected == 25


def test_incident_water_is_not_mistaken_for_requested_water() -> None:
    extractor = EmergencyReportExtractor(known_locations=RESPONSE_LOCATIONS)

    incident = extractor.extract("Riverside Shelter reporting flood water.")

    assert incident.incident_type == "flood"
    assert incident.requested_resource is None


def test_numeric_street_address_is_preserved() -> None:
    extractor = EmergencyReportExtractor(known_locations=RESPONSE_LOCATIONS)

    incident = extractor.extract(
        "Flooding at 123 Main Street. Six residents stranded."
    )

    assert incident.location == "123 Main Street"


def test_extraction_assessment_requires_operator_review() -> None:
    extractor = EmergencyReportExtractor(known_locations=RESPONSE_LOCATIONS)

    assessment = extractor.extract_with_assessment("Requesting assistance.")

    assert assessment.review_required is True
    assert assessment.confidence < 0.5
    assert "Location requires operator confirmation" in assessment.warnings
