# jobs/enrich_updates.py
import os
import time
import pandas as pd
from app.classify import classify_article

RAW_PATH = "data/updates.csv"
ENRICHED_PATH = "data/enriched_updates.csv"

BATCH_SIZE = 20        # how many rows per API burst
SLEEP_BETWEEN = 2.0    # seconds between calls to be gentle

NEEDED_COLS = [
    "company", "title", "clean_text", "source_url",
    "published_at", "collected_at"
]

def _ensure_str_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Make sure listed columns exist and are plain strings (no NaNs)."""
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df[cols] = df[cols].astype(str).fillna("")
    return df

def load_raw() -> pd.DataFrame:
    if not os.path.exists(RAW_PATH):
        print("No raw updates found.")
        return pd.DataFrame()

    df = pd.read_csv(RAW_PATH)

    # Ensure required string cols exist
    df = _ensure_str_cols(df, ["company", "title", "clean_text", "source_url"])

    # Normalize timestamps (UTC-aware); missing cols are fine
    for col in ["published_at", "collected_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    # Unified reference date for downstream use
    df["date_ref"] = pd.to_datetime(
        df.get("published_at").where(df.get("published_at").notna(), df.get("collected_at")),
        errors="coerce",
        utc=True
    )

    return df

def load_enriched_existing() -> pd.DataFrame:
    """Load previously enriched file; ensure join keys + enrichment cols are strings."""
    if not os.path.exists(ENRICHED_PATH):
        return pd.DataFrame(columns=["company", "source_url", "summary", "category", "impact"])

    try:
        df = pd.read_csv(ENRICHED_PATH)

        # Normalize timestamps if present
        for col in ["published_at", "collected_at"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

        if "date_ref" not in df.columns:
            df["date_ref"] = pd.to_datetime(
                df.get("published_at").where(df.get("published_at").notna(), df.get("collected_at")),
                errors="coerce",
                utc=True
            )

        # Ensure join keys + enrichment cols
        df = _ensure_str_cols(df, ["company", "source_url", "summary", "category", "impact"])
        return df
    except Exception:
        # Return empty but schema-compatible
        return pd.DataFrame(columns=["company", "source_url", "summary", "category", "impact"])

def merge_keep_existing(existing: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    """
    Join on (company, source_url) and keep any existing enrichment.
    """
    keys = ["company", "source_url"]
    enrich_cols = ["summary", "category", "impact"]

    # Ensure required cols exist & are strings on both sides
    for df in (existing, fresh):
        df = _ensure_str_cols(df, keys + enrich_cols)

    merged = fresh.merge(
        existing[keys + enrich_cols],
        on=keys,
        how="left",
        suffixes=("", "_old"),
    )

    # Prefer new values if present; else fall back to existing
    for c in enrich_cols:
        old = f"{c}_old"
        if old in merged.columns:
            # keep current if non-empty; otherwise use old
            merged[c] = merged[c].astype(str)
            merged[old] = merged[old].astype(str)
            merged[c] = merged[c].where(merged[c].str.strip() != "", merged[old])
            merged.drop(columns=[old], inplace=True)

    # Final safety
    merged = _ensure_str_cols(merged, enrich_cols + keys)
    return merged

def enrich_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Fill NaN as blanks and enrich all truly empty rows."""
    enrich_cols = ["summary", "category", "impact"]
    for c in enrich_cols:
        if c not in df.columns:
            df[c] = ""
        # convert NaN to blank
        df[c] = df[c].astype(str).fillna("").replace(["nan", "NaN", "None", "NA"], "")

    def _is_blank(s):
        return s.astype(str).str.strip().eq("") | s.astype(str).str.lower().isin(["nan", "none", "na"])

    mask = _is_blank(df["summary"]) | _is_blank(df["category"]) | _is_blank(df["impact"])
    todo = df[mask].copy()
    print(f"Enriching {len(todo)} rows out of {len(df)} total.")

    if todo.empty:
        print("Nothing to enrich.")
        return df

    rows = []
    for i, row in enumerate(todo.to_dict(orient="records"), start=1):
        comp = str(row.get("company", "") or "")
        title = str(row.get("title", "") or "")
        body = str(row.get("clean_text", "") or "")

        out = classify_article(comp, title, body)

        row["summary"]  = out.get("summary", "").strip()
        row["category"] = out.get("category", "Other").strip()
        row["impact"]   = out.get("impact", "Low").strip().title()
        rows.append(row)

        if i % BATCH_SIZE == 0:
            print(f"...{i} enriched; sleeping {SLEEP_BETWEEN}s")
            time.sleep(SLEEP_BETWEEN)

    enriched_df = pd.DataFrame(rows)

    key_cols = ["company", "source_url"]
    for k in key_cols:
        if k not in df.columns:
            df[k] = ""
        if k not in enriched_df.columns:
            enriched_df[k] = ""

    df = df.set_index(key_cols)
    enriched_df = enriched_df.set_index(key_cols)
    df.update(enriched_df)
    df = df.reset_index()

    return df


def main():
    os.makedirs(os.path.dirname(ENRICHED_PATH), exist_ok=True)

    fresh = load_raw()
    if fresh.empty:
        print("No input data. Exiting.")
        return

    existing = load_enriched_existing()
    merged = merge_keep_existing(existing, fresh)
    enriched = enrich_missing(merged)

    # Save atomically-ish
    tmp = ENRICHED_PATH + ".tmp"
    enriched.to_csv(tmp, index=False)
    os.replace(tmp, ENRICHED_PATH)

    print(f"Enrichment complete. Wrote {ENRICHED_PATH} with {len(enriched)} rows.")

if __name__ == "__main__":
    main()
