"""Compute trending topics from aggregator headlines using n-gram frequency.

Public, no auth. Used by `GET /api/agg/trending`.
"""
import re
from collections import Counter
from typing import Iterable, List, Dict, Set

# Common English stopwords + real-estate filler we never want as a topic.
STOPWORDS: Set[str] = {
    "a", "an", "and", "or", "but", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "of", "for", "with", "by", "as", "from", "into", "over", "under",
    "this", "that", "these", "those", "it", "its", "their", "his", "her", "they", "them",
    "we", "us", "you", "your", "our", "i", "me", "my",
    "do", "does", "did", "doing", "done", "will", "would", "could", "should", "can", "may",
    "has", "have", "had", "having", "not", "no", "yes", "all", "any", "some", "more", "most",
    "less", "few", "many", "much", "new", "now", "still", "here", "there", "after", "before",
    "up", "down", "out", "off", "than", "then", "so", "if", "while", "about", "between",
    "what", "who", "when", "where", "why", "how", "which", "whose", "amid", "amidst", "via",
    "vs", "vs.", "per", "amid", "amongst",
    # Headline filler
    "says", "say", "said", "report", "reports", "reported", "reportedly", "according",
    "amid", "ahead", "year", "years", "month", "months", "week", "weeks", "day", "days",
    "news", "update", "exclusive", "breaking", "opinion", "guest", "column",
}

# Real-estate trade words that are too generic on their own to be a "topic".
GENERIC_RE: Set[str] = {
    "real", "estate", "housing", "home", "homes", "house", "houses", "market", "markets",
    "industry", "agent", "agents", "broker", "brokers", "buyer", "buyers", "seller", "sellers",
    "property", "properties", "listing", "listings",
}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]{1,}", flags=re.UNICODE)


def _tokens(title: str) -> List[str]:
    """Lowercased word tokens, with stopwords stripped. Punctuation removed."""
    out: List[str] = []
    for w in WORD_RE.findall(title or ""):
        wl = w.lower()
        if wl in STOPWORDS:
            continue
        if len(wl) < 3:
            continue
        out.append(wl)
    return out


def _ngrams(tokens: List[str], n: int) -> Iterable[str]:
    if len(tokens) < n:
        return
    for i in range(len(tokens) - n + 1):
        yield " ".join(tokens[i : i + n])


def compute_trending(titles: List[str], limit: int = 10) -> List[Dict]:
    """Score bigrams and trigrams across all titles, return the top `limit`
    topics with their occurrence counts. We prefer trigrams over bigrams when
    they substantially overlap, so we don't list both "mortgage rate" and
    "mortgage rate drop" when one fully contains the other."""
    bigrams: Counter = Counter()
    trigrams: Counter = Counter()
    # Per-topic article indices so we can attribute click-throughs later if needed.
    article_idx: Dict[str, List[int]] = {}

    for i, title in enumerate(titles):
        toks = _tokens(title)
        # Bigrams
        for g in _ngrams(toks, 2):
            a, b = g.split(" ", 1)
            # Skip pure-generic n-grams ("real estate", "housing market", ...)
            if a in GENERIC_RE and b in GENERIC_RE:
                continue
            bigrams[g] += 1
            article_idx.setdefault(g, []).append(i)
        # Trigrams
        for g in _ngrams(toks, 3):
            parts = g.split(" ")
            if all(p in GENERIC_RE for p in parts):
                continue
            trigrams[g] += 1
            article_idx.setdefault(g, []).append(i)

    # Prefer trigrams that occur >=2 times; fall back to bigrams that occur >=2 times.
    scored: List[tuple] = []
    seen: Set[str] = set()

    for g, c in trigrams.most_common():
        if c < 2:
            break
        scored.append((g, c, "trigram"))
        seen.add(g)

    for g, c in bigrams.most_common():
        if c < 2:
            break
        # Skip a bigram if a trigram already in `scored` contains it.
        contained = False
        for s, _sc, _kind in scored:
            if g in s:
                contained = True
                break
        if contained:
            continue
        scored.append((g, c, "bigram"))

    scored.sort(key=lambda t: (-t[1], t[0]))
    out = []
    for g, c, kind in scored[:limit]:
        out.append({
            "topic": g,
            "count": c,
            "kind": kind,
            "article_indices": article_idx.get(g, [])[:10],
        })
    return out
