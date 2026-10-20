#!/usr/bin/env python3
"""Provenance audit of PeMS-derived traffic-forecasting benchmarks.

Caltrans PeMS publishes, for every station and 5-minute interval, a "% observed" value: 100 means every
lane was measured, 0 means the whole value was imputed. This tool matches released benchmark files
against the PeMS station_5min records they were built from, cell by cell, and reports how many
benchmark values are PeMS imputations.

Subcommands
    pems-bay   PEMS-BAY (Li et al., ICLR 2018): pems-bay.h5, columns are PeMS station IDs, speed.
    astgcn     PEMS04 / PEMS08 style .npz (Guo et al., AAAI 2019): no station IDs, so each node is first
               re-identified as a PeMS station by matching its flow series, then audited.
    summary    Share of measured / partial / imputed intervals in any set of PeMS station_5min files,
               optionally per month or restricted to a station list.

Examples
    pems_audit.py pems-bay --h5 pems-bay.h5 --pems-dir pems/d04/2017
    pems_audit.py astgcn --npz pems04.npz --start 2018-01-01 --pems-dir pems/d04/2018
    pems_audit.py astgcn --npz pems08.npz --start 2016-07-01 --pems-dir pems/d08/2016
    pems_audit.py summary --pems-dir pems/d04/2017 --from 2017-01-01 --to 2017-06-30 --by-month

--pems-dir holds PeMS Clearinghouse "station_5min" files (dDD_text_station_5min_YYYY_MM_DD.txt.gz) as
downloaded; only files whose date falls inside the benchmark's window are read.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# PeMS station_5min layout (no header): 12 station columns, then 8 lanes x 5 columns.
PEMS_COLS = {"ts": "VARCHAR", "station": "INTEGER", "district": "INTEGER", "fwy": "INTEGER", "dir": "VARCHAR",
             "lane_type": "VARCHAR", "length": "DOUBLE", "samples": "INTEGER", "pct_observed": "INTEGER",
             "total_flow": "DOUBLE", "avg_occ": "DOUBLE", "avg_speed": "DOUBLE"}
for _i in range(1, 9):
    PEMS_COLS.update({f"l{_i}_samples": "INTEGER", f"l{_i}_flow": "DOUBLE", f"l{_i}_occ": "DOUBLE",
                      f"l{_i}_speed": "DOUBLE", f"l{_i}_observed": "INTEGER"})
FILE_DATE = re.compile(r"_(\d{4})_(\d{2})_(\d{2})\.txt\.gz$")
CLASS_SQL = """CASE WHEN p.pct_observed IS NULL THEN 'no PeMS record'
                    WHEN p.pct_observed = 100 THEN 'measured'
                    WHEN p.pct_observed = 0 THEN 'imputed' ELSE 'partial' END"""


def sql_str(s: str) -> str:
    """Quote a value (e.g. a file path) as a SQL string literal."""
    return "'" + str(s).replace("'", "''") + "'"


def pems_files(pems_dir: Path, first: date, last: date) -> list[str]:
    """station_5min files under pems_dir (recursively) whose filename date is within [first, last]."""
    out, seen = [], set()
    for f in sorted(pems_dir.rglob("*station_5min_*.txt.gz")):
        m = FILE_DATE.search(f.name)
        if m and first <= date(*map(int, m.groups())) <= last:
            if f.name in seen:
                sys.exit(f"duplicate PeMS file {f.name} under {pems_dir}; keep one copy per day")
            seen.add(f.name)
            out.append(str(f))
    expected = (last - first).days + 1
    if len(out) != expected:
        print(f"warning: {len(out)} PeMS files for {expected} days in {first}..{last}", file=sys.stderr)
    if not out:
        sys.exit(f"no station_5min files for {first}..{last} under {pems_dir}")
    return out


def load_pems(con, files, stations=None):
    cols = ", ".join(f"'{k}': '{v}'" for k, v in PEMS_COLS.items())
    where = f"WHERE station IN ({','.join(map(str, stations))})" if stations is not None else ""
    con.execute(f"""
        CREATE OR REPLACE TABLE p AS
        SELECT strptime(ts, '%m/%d/%Y %H:%M:%S') AS t, station, pct_observed, total_flow, avg_speed
        FROM read_csv([{", ".join(sql_str(f) for f in files)}], header=false, columns={{{cols}}}, compression='gzip')
        {where}""")
    dups = con.execute("SELECT count(*) FROM (SELECT station, t FROM p GROUP BY 1, 2 HAVING count(*) > 1)").fetchone()[0]
    if dups:
        sys.exit(f"{dups} duplicate (station, timestamp) rows in the PeMS files; cannot match unambiguously")


def report(con, pems_col: str, title: str):
    """Expects table b(t, station, v). Joins to PeMS and summarises by PeMS provenance class."""
    con.execute(f"""
        CREATE OR REPLACE TABLE j AS
        SELECT b.t, b.station, b.v, p.pct_observed, p.{pems_col} AS pv, {CLASS_SQL} AS cls
        FROM b LEFT JOIN p USING (t, station)""")
    total = con.execute("SELECT count(*) FROM j").fetchone()[0]
    assert total == con.execute("SELECT count(*) FROM b").fetchone()[0], "join changed the number of cells"
    print(f"\n{title}: {total:,} benchmark cells")
    print(f"{'PeMS class':<16}{'cells':>14}{'share':>9}{'identical':>11}{'PeMS blank':>12}")
    for cls, n, ident, blank in con.execute("""
            SELECT cls, count(*), sum(CASE WHEN v = pv THEN 1 ELSE 0 END), sum(CASE WHEN pv IS NULL THEN 1 ELSE 0 END)
            FROM j GROUP BY cls ORDER BY count(*) DESC""").fetchall():
        print(f"{cls:<16}{n:>14,}{100 * n / total:>8.1f}%{100 * ident / n:>10.2f}%{blank:>12,}")
    n_ident = con.execute("SELECT count(*) FROM j WHERE v = pv").fetchone()[0]
    rest = con.execute("""
        SELECT count(*), coalesce(sum(CASE WHEN v = 0 THEN 1 ELSE 0 END), 0) FROM j WHERE pv IS NULL""").fetchone()
    diff = con.execute("SELECT count(*) FROM j WHERE pv IS NOT NULL AND v <> pv").fetchone()[0]
    print(f"identical to PeMS: {n_ident:,} of {total:,} cells; PeMS value blank or no record: {rest[0]:,} "
          f"(benchmark holds 0 in {rest[1]:,} of them); present in both but different: {diff:,}")
    return con.execute("SELECT cls, count(*) FROM j GROUP BY cls").fetchall()


def cmd_pems_bay(a):
    import h5py  # only this subcommand needs it
    f = h5py.File(a.h5, "r")
    stations = f["speed/block0_items"][:].astype(int)      # column order of block0_values
    assert sorted(stations) == sorted(f["speed/axis0"][:].astype(int)), "unexpected HDF5 layout"
    t = f["speed/axis1"][:].astype("datetime64[ns]")
    v = f["speed/block0_values"][:]
    assert v.shape == (len(t), len(stations)), "unexpected HDF5 layout"
    first = pd.Timestamp(t.min()).date()
    last = pd.Timestamp(t.max()).date()
    print(f"PEMS-BAY: {len(stations)} sensors x {len(t)} steps, {first} -> {last}")
    con = duckdb.connect()
    con.register("b_df", pd.DataFrame({"t": np.repeat(t, len(stations)), "station": np.tile(stations, len(t)),
                                       "v": v.ravel()}))
    con.execute("CREATE TABLE b AS SELECT * FROM b_df")
    load_pems(con, pems_files(Path(a.pems_dir), first, last), stations.tolist())
    report(con, "avg_speed", "PEMS-BAY speed vs PeMS avg_speed")
    if a.per_sensor:
        con.execute(f"""COPY (SELECT station, count(*) AS cells,
                   round(100.0 * avg(CASE WHEN cls = 'imputed' THEN 1 ELSE 0 END), 2) AS pct_imputed,
                   round(100.0 * avg(CASE WHEN cls = 'measured' THEN 1 ELSE 0 END), 2) AS pct_measured
                FROM j GROUP BY station ORDER BY station) TO {sql_str(a.per_sensor)} (HEADER)""")
        print(f"per-sensor table -> {a.per_sensor}")


def cmd_astgcn(a):
    x = np.load(a.npz, allow_pickle=False)["data"]          # (T, N, 3): flow, occupancy, speed
    T, N, _ = x.shape
    t = np.datetime64(f"{a.start}T00:00") + np.arange(T) * np.timedelta64(5, "m")
    first, last = date.fromisoformat(a.start), pd.Timestamp(t[-1]).date()
    print(f"{Path(a.npz).name}: {N} nodes x {T} steps, assumed {first} -> {last}")
    con = duckdb.connect()
    load_pems(con, pems_files(Path(a.pems_dir), first, last))

    # Re-identification. Candidates: PeMS stations whose total_flow equals the node's flow on >= 95% of the
    # 288 steps of ANY of the first `days` days (several days, so a node whose first day is flat or matches
    # another station by coincidence still finds its station). Several stations can share an identical
    # series (often imputed ones), so each candidate is then scored by identical cells over the whole
    # window and the best score wins.
    day, thr, days = 288, int(0.95 * 288), min(a.days, T // 288)
    k = days * day
    con.register("nf_df", pd.DataFrame({"node": np.tile(np.arange(N), k), "t": np.repeat(t[:k], N),
                                        "d": np.repeat(np.arange(k) // day, N), "flow": x[:k, :, 0].ravel()}))
    con.execute(f"""
        CREATE TABLE cand AS
        SELECT DISTINCT node, station FROM (
            SELECT nf.node, p.station, nf.d FROM nf_df nf JOIN p ON p.t = nf.t AND p.total_flow = nf.flow
            GROUP BY 1, 2, 3 HAVING count(*) >= {thr})""")
    con.register("b_df", pd.DataFrame({"t": np.repeat(t, N), "node": np.tile(np.arange(N), T),
                                       "v": x[:, :, 0].ravel()}))
    con.execute("""
        CREATE TABLE sc AS
        SELECT c.node, c.station, sum(CASE WHEN p.total_flow = b.v THEN 1 ELSE 0 END) AS eq,
               sum(CASE WHEN p.pct_observed = 0 THEN 1 ELSE 0 END) AS n_imp
        FROM cand c JOIN b_df b ON b.node = c.node JOIN p ON p.station = c.station AND p.t = b.t
        GROUP BY c.node, c.station""")
    # Fallback for nodes with no candidate or a weak best match (< 99% of steps identical): score every
    # station over the whole window. Only a few nodes need it, so the exhaustive search stays cheap.
    weak_nodes = [r[0] for r in con.execute(f"""
        SELECT n.node FROM (SELECT unnest(range({N})) AS node) n LEFT JOIN sc USING (node)
        GROUP BY n.node HAVING coalesce(max(sc.eq), 0) < {0.99 * T}""").fetchall()]
    if weak_nodes:
        con.execute(f"""
            INSERT INTO sc
            SELECT b.node, p.station, sum(CASE WHEN p.total_flow = b.v THEN 1 ELSE 0 END) AS eq,
                   sum(CASE WHEN p.pct_observed = 0 THEN 1 ELSE 0 END) AS n_imp
            FROM b_df b JOIN p ON p.t = b.t
            WHERE b.node IN ({",".join(map(str, weak_nodes))})
              AND (b.node, p.station) NOT IN (SELECT node, station FROM sc)
            GROUP BY b.node, p.station HAVING sum(CASE WHEN p.total_flow = b.v THEN 1 ELSE 0 END) > 0""")
        print(f"full-window search for {len(weak_nodes)} node(s) without a strong first-days match")
    # stations tied for the best full-window score; any of them is an equally valid identification
    con.execute("""
        CREATE TABLE tied AS
        SELECT * FROM (SELECT *, max(eq) OVER (PARTITION BY node) AS best FROM sc) WHERE eq = best""")
    con.execute("CREATE TABLE m AS SELECT node, min(station) AS station, count(*) AS n_tied FROM tied GROUP BY node")
    ok, multi = con.execute("SELECT count(*), count(*) FILTER (WHERE n_tied > 1) FROM m").fetchone()
    full = con.execute(f"SELECT count(*) FROM tied WHERE eq = {T}").fetchone()[0]
    print(f"nodes re-identified as PeMS stations: {ok} / {N}; "
          f"{multi} node(s) tied between stations over the full window")
    if ok < N:
        sys.exit(f"{N - ok} node(s) not re-identified; check --start and --pems-dir (no partial results reported)")
    weak = con.execute(f"SELECT node, station, best FROM tied WHERE best < {0.99 * T} GROUP BY ALL ORDER BY best").fetchall()
    if weak:
        print(f"note: {len(weak)} node(s) match their station on < 99% of steps (node, station, identical steps): "
              + ", ".join(f"({n}, {s}, {b})" for n, s, b in weak[:10]))
    dup = con.execute("SELECT count(*) FROM (SELECT station FROM m GROUP BY station HAVING count(*) > 1)").fetchone()[0]
    if dup:
        print(f"warning: {dup} PeMS station(s) assigned to more than one node", file=sys.stderr)
    # bound the effect of tie choices on the imputed share: per node, the smallest and largest imputed count
    # among its tied stations
    lo, hi = con.execute("""SELECT sum(mn), sum(mx) FROM (
                               SELECT node, min(n_imp) AS mn, max(n_imp) AS mx FROM tied GROUP BY node)""").fetchone()
    print(f"fully imputed share across all tie choices: {100 * lo / (T * N):.2f}% .. {100 * hi / (T * N):.2f}% "
          f"(stations tied with identical values over all {T} steps: {full} node-station pairs)")
    if a.mapping:
        con.execute(f"COPY (SELECT node, station, n_tied FROM m ORDER BY node) TO {sql_str(a.mapping)} (HEADER)")
        print(f"node -> station mapping -> {a.mapping}")
    con.execute("CREATE TABLE b AS SELECT b_df.t, m.station, b_df.v FROM b_df JOIN m USING (node)")
    assert con.execute("SELECT count(*) FROM b").fetchone()[0] == T * N
    report(con, "total_flow", f"{Path(a.npz).name} flow vs PeMS total_flow (re-identified nodes; lowest station ID among ties)")


def cmd_summary(a):
    first, last = date.fromisoformat(a.date_from), date.fromisoformat(a.date_to)
    con = duckdb.connect()
    stations = None
    if a.stations:
        stations = [int(s) for s in re.findall(r"^\s*(\d+)", Path(a.stations).read_text(), re.M)]
    load_pems(con, pems_files(Path(a.pems_dir), first, last), stations)
    group = "strftime(t, '%Y-%m')" if a.by_month else "'all'"
    print(f"{'period':<9}{'stations':>9}{'intervals':>14}{'measured':>10}{'partial':>9}{'imputed':>9}"
          f"{'no % obs':>10}")
    for r in con.execute(f"""
            SELECT {group} AS g, count(DISTINCT station), count(*),
                   100.0 * avg(CASE WHEN pct_observed = 100 THEN 1 ELSE 0 END),
                   100.0 * avg(CASE WHEN pct_observed > 0 AND pct_observed < 100 THEN 1 ELSE 0 END),
                   100.0 * avg(CASE WHEN pct_observed = 0 THEN 1 ELSE 0 END),
                   count(*) FILTER (WHERE pct_observed IS NULL)
            FROM p GROUP BY 1 ORDER BY 1""").fetchall():
        print(f"{r[0]:<9}{r[1]:>9,}{r[2]:>14,}{r[3]:>9.1f}%{r[4]:>8.1f}%{r[5]:>8.1f}%{r[6]:>10,}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pems-bay", help="audit pems-bay.h5")
    s.add_argument("--h5", required=True)
    s.add_argument("--pems-dir", required=True)
    s.add_argument("--per-sensor", help="write a per-sensor CSV here")
    s.set_defaults(fn=cmd_pems_bay)
    s = sub.add_parser("astgcn", help="audit an ASTGCN-style npz (PEMS04, PEMS08)")
    s.add_argument("--npz", required=True)
    s.add_argument("--start", required=True, help="first day of the benchmark, YYYY-MM-DD")
    s.add_argument("--pems-dir", required=True)
    s.add_argument("--mapping", help="write the node -> PeMS station mapping CSV here")
    s.add_argument("--days", type=int, default=3, help="days used to find candidate stations (default 3)")
    s.set_defaults(fn=cmd_astgcn)
    s = sub.add_parser("summary", help="measured / partial / imputed shares in PeMS files")
    s.add_argument("--pems-dir", required=True)
    s.add_argument("--from", dest="date_from", required=True)
    s.add_argument("--to", dest="date_to", required=True)
    s.add_argument("--stations", help="file whose lines start with a PeMS station ID (e.g. a sensor CSV)")
    s.add_argument("--by-month", action="store_true")
    s.set_defaults(fn=cmd_summary)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
