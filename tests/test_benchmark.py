from reliefrelay.benchmark import word_error_rate


def test_word_error_rate_normalizes_case_and_punctuation() -> None:
    assert word_error_rate("Fire at North Clinic.", "fire at north clinic") == 0.0


def test_word_error_rate_counts_substitutions() -> None:
    assert word_error_rate("three people injured", "two people injured") == 0.3333
