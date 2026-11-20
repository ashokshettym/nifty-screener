"""Headline analysis: VADER (handles negation/intensity) + finance word list + strict order-win regex + recency weighting."""
import re, threading
from datetime import datetime, timezone
FIN = {"beats": 2, "surge": 2, "surges": 2, "record": 1.5, "upgrade": 2, "upgrades": 2, "rally": 2, "jumps": 1.8, "rises": 1.2,
       "bags": 1.8, "bagged": 1.8, "wins": 1.8, "awarded": 1.5, "buyback": 1.5, "dividend": 1, "outperform": 2,
       "downgrade": -2, "downgrades": -2, "probe": -2, "fraud": -3, "penalty": -2, "slump": -2.3, "plunge": -2.5, "tumble": -2.2,
       "misses": -2, "miss": -1.5, "default": -2.5, "raid": -2.5, "loss": -1.8, "cuts": -1.5, "falls": -1.5, "drops": -1.5,
       "layoffs": -1.8, "resigns": -1.2, "lawsuit": -1.8, "ban": -1.8}
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _v = SentimentIntensityAnalyzer(); _v.lexicon.update(FIN)
except Exception:
    _v = None   # falls back to the word list only
ORDER_RE = re.compile(r"\b(bags?|bagged|wins?|won|secures?|secured|receives?|received|awarded|lands?|gets?)\b.{0,60}\b(orders?|contracts?|loa|letter of award)\b"
                      r"|\b(orders?|contracts?)\b.{0,15}\b(worth|valued|of rs|of ₹)", re.I)
NEG_ORDER = re.compile(r"cancel|terminat|loses?|lost|scrap|blacklist|delay", re.I)

MODE = "vader"; _fb = None; _lock = threading.Lock()
def set_mode(m):
    global MODE; MODE = m
def finbert_available():
    try:
        import transformers, torch  # noqa
        return True
    except Exception:
        return False
def finbert_scores(titles):
    """ProsusAI/finbert, positive minus negative probability per headline (-1..1). None if unavailable."""
    global _fb
    try:
        with _lock:                                     # one model, shared by the worker threads
            if _fb is None:
                from transformers import pipeline
                _fb = pipeline("text-classification", model="ProsusAI/finbert", top_k=None, truncation=True)
            res = _fb(titles, batch_size=16)
        out = []
        for r in res:
            d = {x["label"].lower(): x["score"] for x in r}
            out.append(d.get("positive", 0) - d.get("negative", 0))
        return out
    except Exception as e:
        print("FinBERT failed, using VADER:", e); return None

def score_text(t):
    if _v: return _v.polarity_scores(t)["compound"]
    s = sum(FIN.get(w, 0) for w in re.findall(r"[a-z']+", t.lower()))
    return max(-1.0, min(1.0, s/4))

def age_days(s):
    try: return max((datetime.now(timezone.utc) - datetime.fromisoformat(s.replace("Z", "+00:00"))).days, 0)
    except Exception: return 7

def annotate(news):
    tones = finbert_scores([n["title"] for n in news]) if MODE == "finbert" and news else None
    for i, n in enumerate(news):
        n["age"] = age_days(n.get("date", "")); t = n["title"]
        n["order"] = bool(ORDER_RE.search(t)) and not NEG_ORDER.search(t) and n["age"] <= 90
        n["tone"] = tones[i] if tones else score_text(t); n["w"] = 0.5 ** (n["age"]/7)     # newer headlines count more
    return news

def aggregate(news):
    w = sum(n["w"] for n in news)
    return sum(n["tone"]*n["w"] for n in news)/w if w else 0.0
