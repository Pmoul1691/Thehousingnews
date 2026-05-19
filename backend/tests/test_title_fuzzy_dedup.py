"""Unit tests for title-based fuzzy dedup in the aggregator.

The existing URL-based dedup catches a story re-shared with different
tracking params. But two publishers will often re-title the SAME wire story
("Fed signals rate cut" vs "Fed Signals Rate Cut In June - WSJ"). These
tests lock in the title normalizer and the near-duplicate predicate that
sits in front of the agg_articles upsert.
"""
from services.rss_ingest import (
    normalize_title,
    title_signature,
    titles_are_near_duplicates,
)


# ---------- normalize_title ----------

def test_normalize_title_lowercases_and_strips_punctuation():
    assert normalize_title("Fed Signals Rate Cut!") == "fed signals rate cut"


def test_normalize_title_drops_publisher_suffix_pipe():
    assert normalize_title("Fed signals rate cut | Bloomberg") == "fed signals rate cut"


def test_normalize_title_drops_publisher_suffix_hyphen():
    assert normalize_title("Fed signals rate cut - WSJ") == "fed signals rate cut"


def test_normalize_title_drops_em_dash_publisher_suffix():
    assert normalize_title("Fed signals rate cut \u2014 The New York Times") == "fed signals rate cut"


def test_normalize_title_drops_breaking_prefix():
    assert normalize_title("BREAKING: Fed signals rate cut") == "fed signals rate cut"


def test_normalize_title_drops_exclusive_prefix():
    assert normalize_title("Exclusive - Fed signals rate cut") == "fed signals rate cut"


def test_normalize_title_drops_stopwords():
    # "the" / "a" / "in" should disappear; rest of the meaning carries.
    assert normalize_title("The Fed cuts rates in June") == "fed cuts rates june"


def test_normalize_title_handles_empty_input():
    assert normalize_title("") == ""
    assert normalize_title(None) == ""  # type: ignore[arg-type]


# ---------- title_signature ----------

def test_signature_stable_across_punctuation_and_case():
    a = title_signature("Fed Signals Rate Cut!")
    b = title_signature("fed signals rate cut")
    assert a and a == b


def test_signature_strips_publisher_branding():
    a = title_signature("Fed signals rate cut | Bloomberg")
    b = title_signature("Fed signals rate cut - WSJ")
    assert a == b


def test_signature_differs_for_genuinely_different_stories():
    assert title_signature("Fed signals rate cut") != title_signature("Mortgage rates climb again")


# ---------- titles_are_near_duplicates ----------

def test_near_dup_exact_normalized_match():
    a = normalize_title("Fed signals rate cut | Bloomberg")
    b = normalize_title("Fed Signals Rate Cut - WSJ")
    assert titles_are_near_duplicates(a, b)


def test_near_dup_minor_rewording():
    """One publisher trims "in June" — should still be flagged."""
    a = normalize_title("Fed signals rate cut in June - WSJ")
    b = normalize_title("Fed signals rate cut in June | Bloomberg")
    assert titles_are_near_duplicates(a, b)


def test_not_a_dup_different_stories():
    a = normalize_title("Fed signals rate cut")
    b = normalize_title("Mortgage applications surge 12 percent")
    assert not titles_are_near_duplicates(a, b)


def test_not_a_dup_similar_topic_different_subject():
    a = normalize_title("Blackstone buys Phoenix portfolio")
    b = normalize_title("KKR sells Dallas portfolio")
    assert not titles_are_near_duplicates(a, b)


def test_empty_titles_are_never_near_dup():
    assert not titles_are_near_duplicates("", "")
    assert not titles_are_near_duplicates("fed cuts rates", "")
