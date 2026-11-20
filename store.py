import json, pathlib
import pandas as pd
F = pathlib.Path(__file__).parent / "data" / "state.json"
F.parent.mkdir(exist_ok=True)
def load():
    try: s = json.loads(F.read_text())
    except Exception: s = {}
    return {"watchlist": s.get("watchlist", []), "portfolio": s.get("portfolio", [])}
def save(s): F.write_text(json.dumps(s, indent=1))
def clean(df):
    return [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in df.to_dict("records")]
