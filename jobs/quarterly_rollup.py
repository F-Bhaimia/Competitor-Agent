# jobs/quarterly_rollup.py
import os
import pandas as pd
from datetime import datetime

DATA_ENRICHED = "data/enriched_updates.csv"
DATA_RAW = "data/updates.csv"
OUT_DIR = "exports"
OUT_CSV = os.path.join(OUT_DIR, "quarterly_rollup.csv")

def load_source():
    path = DATA_ENRICHED if os.path.exists(DATA_ENRICHED) else DATA_RAW
    df = pd.read_csv(path)
    # Parse dates (timezone-aware safe)
    for col in ["published_at", "collected_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    # Build a reference date (published_at fallback to collected_at)
    pub = df.get("published_at")
    col = df.get("collected_at")
    df["date_ref"] = pd.to_datetime(
        (pub.where(pub.notna(), col) if pub is not None else col),
        errors="coerce",
        utc=True,
    )
    # Keep only rows with a reference date
    df = df[df["date_ref"].notna()].copy()
    return df, path

def compute_rollup(df: pd.DataFrame) -> pd.DataFrame:
    # Convert to naive (no timezone) before to_period to avoid tz warning
    df = df.copy()
    if pd.api.types.is_datetime64_any_dtype(df["date_ref"]):
        # if it's tz-aware, drop tz; if it's already naive, this is a no-op
        try:
            df["date_ref_naive"] = df["date_ref"].dt.tz_convert("UTC").dt.tz_localize(None)
        except Exception:
            df["date_ref_naive"] = df["date_ref"].dt.tz_localize(None)

    # Quarter label like 2025-Q4
    df["quarter"] = df["date_ref_naive"].dt.to_period("Q").astype(str)

    base_cols = ["company", "quarter"]
    out = df.groupby(base_cols).size().reset_index(name="post_count")

    # Optional enrichments
    if "category" in df.columns:
        cat = (df
               .groupby(base_cols + ["category"])
               .size()
               .reset_index(name="count_category")
               .pivot_table(index=base_cols, columns="category", values="count_category", fill_value=0)
               .reset_index())
        out = out.merge(cat, on=base_cols, how="left")

    if "impact" in df.columns:
        imp = (df
               .assign(impact=df["impact"].astype(str).str.title())
               .groupby(base_cols + ["impact"])
               .size()
               .reset_index(name="count_impact")
               .pivot_table(index=base_cols, columns="impact", values="count_impact", fill_value=0)
               .reset_index())
        out = out.merge(imp, on=base_cols, how="left")

    # Order nicely
    order_cols = ["company", "quarter", "post_count"]
    other_cols = [c for c in out.columns if c not in order_cols]
    out = out[order_cols + other_cols]
    return out.sort_values(["company", "quarter"])

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df, src = load_source()
    if df.empty:
        print("No data available to roll up.")
        return
    rollup = compute_rollup(df)
    rollup.to_csv(OUT_CSV, index=False)
    print(f"Quarterly roll-up written to {OUT_CSV}")
    print(f"   Source: {src}")
    print(f"   Rows: {len(rollup)}  (companies x quarters)")

if __name__ == "__main__":
    main()
