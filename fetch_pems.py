#!/usr/bin/env python3
"""Download Caltrans PeMS Clearinghouse station_5min files for one district and date range.

    PEMS_USERNAME=... PEMS_PASSWORD=... fetch_pems.py --district 4 --from 2017-01-01 --to 2017-06-30 --out pems/d04/2017

Needs a free PeMS account (https://pems.dot.ca.gov/). Files are saved exactly as served
(dDD_text_station_5min_YYYY_MM_DD.txt.gz, about 15-30 MB each). A file already present with the listed
size is skipped, so the command can be re-run to resume. One file at a time, with a pause between files.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

BASE = "https://pems.dot.ca.gov/"
UA = "pems-provenance-audit/1.0 (research; PeMS account holder)"


def login(s):
    user, pw = os.environ.get("PEMS_USERNAME"), os.environ.get("PEMS_PASSWORD")
    if not user or not pw:
        sys.exit("set PEMS_USERNAME and PEMS_PASSWORD")
    r = s.post(BASE, data={"username": user, "password": pw, "login": "Login"}, timeout=60)
    if "Welcome, " not in r.text:
        sys.exit("PeMS login failed")


def listing(s, district, year):
    r = s.get(BASE, params={"srq": "clearinghouse", "district_id": district, "yy": year,
                            "type": "station_5min", "returnformat": "text"}, timeout=120)
    r.raise_for_status()
    j = r.json()                     # an empty listing comes back as a bare []
    data = j.get("data") if isinstance(j, dict) else None
    return [f for month in data.values() for f in month] if isinstance(data, dict) else []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--district", type=int, required=True)
    ap.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    ap.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between files")
    a = ap.parse_args()

    s = requests.Session()
    s.headers["User-Agent"] = UA
    login(s)
    files = []
    for y in range(a.start.year, a.end.year + 1):
        for f in listing(s, a.district, y):
            m = re.search(r"_(\d{4})_(\d{2})_(\d{2})\.", f["file_name"])
            if m and a.start <= date(*map(int, m.groups())) <= a.end:
                files.append(f)
    print(f"{len(files)} files in window")
    a.out.mkdir(parents=True, exist_ok=True)
    for f in sorted(files, key=lambda f: f["file_name"]):
        dest = a.out / f["file_name"]
        size = int(f["bytes"].replace(",", ""))
        if dest.exists() and dest.stat().st_size == size:
            continue
        for attempt in (1, 2, 3):
            with s.get(BASE, params={"download": f["file_id"], "dnode": "Clearinghouse"}, stream=True, timeout=300) as r:
                if r.status_code == 200 and "html" not in r.headers.get("content-type", ""):
                    part = dest.with_suffix(".part")
                    with part.open("wb") as out:
                        for chunk in r.iter_content(1 << 20):
                            out.write(chunk)
                    if part.stat().st_size == size:
                        part.rename(dest)
                        print(f"{f['file_name']} ok")
                        break
                    part.unlink()
            login(s)                 # an HTML answer means the session expired
            time.sleep(10 * attempt)
        else:
            print(f"{f['file_name']} FAILED", file=sys.stderr)
        time.sleep(a.pause)


if __name__ == "__main__":
    main()
