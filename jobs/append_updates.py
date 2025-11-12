# jobs/append_updates.py
import os
import pandas as pd

RAW_PATH = "data/updates.csv"
NEW_PATH = "data/new_updates.csv"

NEEDED_COLS = ["company","title","clean_text","source_url","published_at","collected_at"]

def ensure_cols(df):
    for c in NEEDED_COLS:
        if c not in df.columns:
            df[c] = ""
    # normalize datetime columns
    for c in ["published_at","collected_at"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=True)
    return df

def main():
    if not os.path.exists(NEW_PATH):
        print(f"No {NEW_PATH} found. Nothing to append.")
        return

    base = pd.read_csv(RAW_PATH) if os.path.exists(RAW_PATH) else pd.DataFrame(columns=NEEDED_COLS)
    add  = pd.read_csv(NEW_PATH)

    base = ensure_cols(base)
    add  = ensure_cols(add)

    # concat then dedupe by (company, source_url), keeping the newest published_at
    merged = pd.concat([base, add], ignore_index=True)

    # Prefer newer published_at for duplicates
    merged["published_at_norm"] = pd.to_datetime(merged["published_at"], errors="coerce", utc=True)
    merged = (merged.sort_values("published_at_norm")
                    .drop(columns=["published_at_norm"]))

    # Keep the latest per (company, source_url)
    merged = merged.drop_duplicates(subset=["company","source_url"], keep="last")

    # Write back
    os.makedirs(os.path.dirname(RAW_PATH), exist_ok=True)
    tmp = RAW_PATH + ".tmp"
    merged.to_csv(tmp, index=False, encoding="utf-8")
    os.replace(tmp, RAW_PATH)

    print(f"Appended {len(add)} rows from {NEW_PATH} into {RAW_PATH}. New total: {len(merged)}")

if __name__ == "__main__":
    main()
