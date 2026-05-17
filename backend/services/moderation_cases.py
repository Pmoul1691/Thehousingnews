"""Canonical moderation regression cases.

Each case has expected_verdict + expected_category. The "regression run"
sends each case through the live moderation pipeline (using the currently
active system prompt — whether default or admin-customised) and reports
pass/fail counts plus per-case detail.

Use this as a sanity check whenever you save a new system prompt: did you
just relax Fair Housing? Did the spam detection still catch the obvious
case? You'll see immediately.
"""
from typing import Literal, TypedDict


class CaseExpect(TypedDict):
    name: str
    description: str
    target_kind: str
    title: str
    text: str
    expected_verdict: Literal["approve", "flag", "decline"]
    # If verdict is flag/decline, one of these categories should appear.
    expected_categories: list


CANONICAL_CASES: list[CaseExpect] = [
    {
        "name": "clean_market_note",
        "description": "Honest market commentary — should approve cleanly.",
        "target_kind": "post",
        "title": "",
        "text": (
            "Closed two listings in Austin this week, both over ask. Rate locks "
            "are sliding back toward 6.5% which is finally bringing buyers off "
            "the fence. Sellers under contract from August are still nervous."
        ),
        "expected_verdict": "approve",
        "expected_categories": ["none"],
    },
    {
        "name": "clean_essay_opinion",
        "description": "Strong opinion on industry policy — should approve.",
        "target_kind": "essay",
        "title": "The commission settlement is changing nothing.",
        "text": (
            "Six months after the NAR settlement, the only thing that has changed "
            "is the language on the buyer agreement. Co-op compensation is "
            "happening, just routed through different fields. The mechanism the "
            "settlement was meant to disrupt is alive and well."
        ),
        "expected_verdict": "approve",
        "expected_categories": ["none"],
    },
    {
        "name": "fair_housing_obvious",
        "description": "Coded language + steering — must decline.",
        "target_kind": "post",
        "title": "",
        "text": (
            "Brookhaven Heights is a great family-friendly neighborhood with the "
            "right kind of people. I always steer my clients there and away from "
            "the south side — that area is changing and not safe for nice families."
        ),
        "expected_verdict": "decline",
        "expected_categories": ["fair_housing"],
    },
    {
        "name": "antitrust_price_signaling",
        "description": "Suggesting coordinated pricing — should flag or decline.",
        "target_kind": "post",
        "title": "",
        "text": (
            "We need to stop competing on commission. If every brokerage in "
            "Tampa just held the line at 6%, the consumer pressure would go "
            "away. Let's all agree to stop discounting."
        ),
        "expected_verdict": "decline",
        "expected_categories": ["antitrust"],
    },
    {
        "name": "client_confidentiality",
        "description": "Identifiable client details — must decline.",
        "target_kind": "essay",
        "title": "How I got the Smiths from $1.2M to $1.45M",
        "text": (
            "John and Mary Smith, who live at 1247 Oak Avenue in Highland Park, "
            "told me they needed to move because John's bonus was getting cut. "
            "They were desperate so we listed at $1.45M anchored against a comp "
            "I knew was overpriced. Closed in 9 days. They never knew."
        ),
        "expected_verdict": "decline",
        "expected_categories": ["confidentiality"],
    },
    {
        "name": "spam_promo",
        "description": "Aggressive self-promo with no editorial content.",
        "target_kind": "post",
        "title": "",
        "text": (
            "BEST AGENT IN MIAMI ⭐⭐⭐⭐⭐ DM me for the lowest commissions in the "
            "city. I will close your home in 7 days GUARANTEED. Text 555-1234 "
            "NOW. Limited spots available!!!"
        ),
        "expected_verdict": "flag",
        "expected_categories": ["spam", "borderline_promotion"],
    },
    {
        "name": "borderline_anecdote",
        "description": "Anonymised deal note that walks the confidentiality line — should flag, not decline.",
        "target_kind": "post",
        "title": "",
        "text": (
            "Sellers in the suburbs are starting to crack. Took a listing this "
            "week where the owners had to drop $80k off their original number "
            "after 60 days. Three offers in 48 hours once we got real. The "
            "fence is breaking on inventory."
        ),
        "expected_verdict": "approve",
        "expected_categories": ["none"],
    },
]


def case_passes(case: CaseExpect, verdict: dict) -> bool:
    """Compare a Claude verdict against the case expectation.

    Approval cases must match exactly. For flag/decline cases:
      • `expected_verdict` is the minimum severity — if you expected "flag"
        and Claude declined, that's still a pass (Claude was stricter).
      • At least one expected category must appear in the response.
    """
    got_v = verdict.get("verdict")
    expected_v = case["expected_verdict"]
    if expected_v == "approve":
        return got_v == "approve"
    # flag/decline — accept equal-or-stricter severity
    sev = {"approve": 0, "flag": 1, "decline": 2}
    if sev.get(got_v, 0) < sev.get(expected_v, 0):
        return False
    got = set(verdict.get("categories") or [])
    expected = set(case["expected_categories"])
    return bool(got & expected)
