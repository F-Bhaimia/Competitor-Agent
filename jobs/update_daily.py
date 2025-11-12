# jobs/update_daily.py
import argparse, os, sys, time, json
from datetime import datetime, timedelta, timezone
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT, "data")
RAW_PATH = os.path.join(DATA_DIR, "updates.csv")
ENRICHED_PATH = os.path.join(DATA_DIR, "enriched_updates.csv")
LOCK_PATH = os.path.join(DATA_DIR, ".update_daily.lock")

def iso_date(s):
    return datetime.fromisoformat(s).date()

def default_since_date():
    # yesterday (UTC) at 00:00
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

def acquire_lock():
    if os.path.exists(LOCK_PATH):
        print("Another update is running (lockfile present). Exiting.")
        sys.exit(0)
    with open(LOCK_PATH, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

def release_lock():
    try:
        if os.path.exists(LOCK_PATH):
            os.remove(LOCK_PATH)
    except Exception:
        pass

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def safe_read_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()

def dedupe(df):
    # keep the most recent by published_at or collected_at
    if "published_at" in df.columns:
        df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce", utc=True)
    if "collected_at" in df.columns:
        df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce", utc=True)
    df = df.sort_values(by=["published_at","collected_at"], ascending=[False, False], na_position="last")
    # define keys
    keys = [c for c in ["company","source_url"] if c in df.columns]
    if keys:
        df = df.drop_duplicates(subset=keys, keep="first")
    return df

def main():
    parser = argparse.ArgumentParser(description="Daily update coordinator: fetch → merge → enrich.")
    parser.add_argument("--since", type=str, default=default_since_date(),
                        help="ISO date (YYYY-MM-DD). Default: yesterday UTC.")
    args = parser.parse_args()

    ensure_data_dir()
    acquire_lock()
    try:
        since = args.since
        print(f"[update_daily] Starting. since={since}")

        # 1) Fetch (calls jobs.fetch_rss: creates/returns a CSV path or prints on stdout)
        #    We call it as a module so it uses the same venv.
        import subprocess
        cmd = [sys.executable, "-m", "jobs.fetch_rss", "--since", since, "--out", RAW_PATH]
        print(f"[update_daily] Running: {' '.join(cmd)}")
        proc = subprocess.run(cmd, text=True, capture_output=True, cwd=ROOT)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            raise SystemExit("[update_daily] fetch_rss failed")

        # 2) Load & dedupe raw file
        raw = safe_read_csv(RAW_PATH)
        if raw.empty:
            print("[update_daily] No rows in updates.csv after fetch (possibly no new items).")
        else:
            raw = dedupe(raw)
            tmp = RAW_PATH + ".tmp"
            raw.to_csv(tmp, index=False, encoding="utf-8")
            os.replace(tmp, RAW_PATH)
            print(f"[update_daily] Raw merged/deduped. rows={len(raw)}")

        # 3) Enrich
        cmd2 = [sys.executable, "-m", "jobs.enrich_updates"]
        print(f"[update_daily] Running: {' '.join(cmd2)}")
        proc2 = subprocess.run(cmd2, text=True, capture_output=True, cwd=ROOT)
        print(proc2.stdout)
        if proc2.returncode != 0:
            print(proc2.stderr)
            raise SystemExit("[update_daily] enrich_updates failed")

        # 4) Done
        enr = safe_read_csv(ENRICHED_PATH)
        print(f"[update_daily] Done. enriched={len(enr)} rows at {ENRICHED_PATH}")
    finally:
        release_lock()

if __name__ == "__main__":
    main()
