import re


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def word_error_rate(reference: str, hypothesis: str) -> float:
    expected = _words(reference)
    actual = _words(hypothesis)
    previous = list(range(len(actual) + 1))
    for expected_index, expected_word in enumerate(expected, start=1):
        current = [expected_index]
        for actual_index, actual_word in enumerate(actual, start=1):
            substitution_cost = 0 if expected_word == actual_word else 1
            current.append(
                min(
                    previous[actual_index] + 1,
                    current[actual_index - 1] + 1,
                    previous[actual_index - 1] + substitution_cost,
                )
            )
        previous = current
    return round(previous[-1] / max(1, len(expected)), 4)
