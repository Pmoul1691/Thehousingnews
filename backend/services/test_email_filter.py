"""Detects emails that look like automated-test / e2e accounts.

Shared between the offline suspend script and the live API endpoints so we
never accidentally surface test accounts in any public-facing list. This
lives in services/ (not scripts/) because routes import from it on request.
"""
import re

# Patterns we recognise as obvious test artefacts. Keep this list
# conservative — anything borderline should be reviewed manually before
# adding here. The regex matches the WHOLE email (case-insensitive).
_TEST_EMAIL_PATTERNS = [
    r"^e2e\..*",                # e2e.signup.*, e2e.dup.*, etc.
    r"^auth\.smoke\..*",        # auth.smoke.1779119938@...
    r"^perf-test@.*",           # perf-test@example.com (Day-2 audit probe)
    r".*@example\.com$",        # the canonical example.com TLD
    r".*@example\.org$",
    r".*@example\.net$",
    r".*@test\..*",             # *@test.local, *@test.com, etc.
    r".*\.test$",               # *@something.test
    r"^test[\.\-_+].*@.*",      # test.foo@..., test+x@..., test_bar@...
    r"^smoke[\.\-_+].*@.*",     # smoke.*@... — engagement-tracking smoke admin
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _TEST_EMAIL_PATTERNS]


def is_test_email(email: str) -> bool:
    """Return True if the email looks like a test/e2e fixture, False otherwise.
    Empty strings and None safely return False so this is safe to drop into
    a list comprehension over arbitrary user rows."""
    if not email or not isinstance(email, str):
        return False
    e = email.strip().lower()
    return any(p.match(e) for p in _COMPILED)
