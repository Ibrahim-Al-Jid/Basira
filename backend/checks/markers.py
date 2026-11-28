"""Results that are not a verdict: a check the submitted capture cannot support."""


class Incomplete:
    """A check that was not measured, and why."""

    def __init__(self, reason):
        self.reason = reason

    def __repr__(self):
        return f"Incomplete({self.reason!r})"


HEADERS_INCOMPLETE = Incomplete("har_headers_incomplete")
CONTENT_UNREADABLE = Incomplete("response_content_unreadable")


def missing(complete):
    """The marker for a check that needed data this capture does not carry."""
    return HEADERS_INCOMPLETE if not complete else CONTENT_UNREADABLE
