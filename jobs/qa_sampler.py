# jobs/qa_sampler.py
import os
import pandas as pd
from datetime import datetime

SRC = "data/enriched_updates.csv"
OUT_DIR = "exports"
DEFAULT_FRACTION = 0.10  # ~10%

def main(fraction: float = DEFAULT_FRACTION, min_rows: int = 15, seed: int = 42):
    if not os.path.exists(SRC):
        print("No enriched file found. Run jobs.enrich_updates first.")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(SRC)

    # Prefer rows that actually have enrichment
    has_summary = df.get("summary", "").astype(str).str.strip().ne("")
    has_category = df.get("category", "").astype(str).str.strip().ne("")
    has_impact = df.get("impact", "").astype(str).str.strip().ne("")
    dfq = df[has_summary & has_category & has_impact].copy()
    if dfq.empty:
        print("No enriched rows available.")
        return

    n = max(min_rows, int(len(dfq) * fraction))
    sample = dfq.sample(n=min(n, len(dfq)), random_state=seed)

    # light columns for QA
    keep = [c for c in ["date_ref","company","title","category","impact","summary","source_url"] if c in sample.columns]
    sample = sample[keep].copy()

    ts = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(OUT_DIR, f"qa_sample_{ts}.csv")
    sample.to_csv(out_path, index=False)
    print(f"QA sample written to {out_path} (rows: {len(sample)})")

if __name__ == "__main__":
    main()
