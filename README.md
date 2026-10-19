# pems-provenance-audit

**Three widely used PeMS traffic benchmarks contain unflagged imputed values.**

Caltrans PeMS marks every 5-minute detector value with how much of it was measured (`% observed`). The
PEMS-BAY, PEMS04 and PEMS08 benchmarks drop that marking. This repository matches the released benchmark
files against the PeMS records they came from, cell by cell.

| Benchmark | Cells | Fully imputed by PeMS | Identical to PeMS |
|---|---|---|---|
| PEMS-BAY (speed, Jan–Jun 2017) | 16,937,700 | **24.5%** | every cell PeMS has a value for (521 zeros mark PeMS gaps) |
| PEMS04 (flow, Jan–Feb 2018) | 5,216,544 | **31.8%** | 100% |
| PEMS08 (flow, Jul–Aug 2016) | 3,035,520 | **48.1%** | 100% |

PEMS04 and PEMS08 ship without PeMS station IDs; the tool re-identifies every node (307/307, 170/170).
They also contain groups of identical, wholly imputed nodes (20 of 307 and 25 of 170).

Full write-up: [`report/report.md`](report/report.md) and `report/report.pdf`.

## Reproduce

Needs Python 3.11+ (tested on 3.12), a free PeMS account (https://pems.dot.ca.gov/), about 7.5 GB of disk
for the PeMS files and about 8 GB of RAM. Each audit runs in under 10 seconds on a 24-core workstation.

```sh
python -m venv venv && venv/bin/pip install -r requirements.txt

# 1. PeMS station_5min files for the benchmark windows (one file per day, ~7.5 GB total)
export PEMS_USERNAME=... PEMS_PASSWORD=...
venv/bin/python fetch_pems.py --district 4 --from 2017-01-01 --to 2017-06-30 --out pems/d04/2017
venv/bin/python fetch_pems.py --district 4 --from 2018-01-01 --to 2018-02-28 --out pems/d04/2018
venv/bin/python fetch_pems.py --district 8 --from 2016-07-01 --to 2016-08-31 --out pems/d08/2016

# 2. Benchmark files from the authors, placed in this directory
#    pems-bay.h5: Google Drive folder linked from https://github.com/liyaguang/DCRNN (README, "Data Preparation")
#    pems04.npz, pems08.npz: https://github.com/wanhuaiyu/ASTGCN, files data/PEMS04/pems04.npz and data/PEMS08/pems08.npz
shasum -a 256 -c checksums.sha256      # Linux: sha256sum -c checksums.sha256

# 3. Audit
venv/bin/python pems_audit.py pems-bay --h5 pems-bay.h5 --pems-dir pems/d04/2017 --per-sensor bay_per_sensor.csv
venv/bin/python pems_audit.py astgcn --npz pems04.npz --start 2018-01-01 --pems-dir pems/d04/2018 --mapping pems04_map.csv
venv/bin/python pems_audit.py astgcn --npz pems08.npz --start 2016-07-01 --pems-dir pems/d08/2016 --mapping pems08_map.csv

# Context: measured / partial / imputed shares in any PeMS files, optionally for a station list
venv/bin/python pems_audit.py summary --pems-dir pems/d04/2017 --from 2017-01-01 --to 2017-06-30 --by-month
```

`report/make_figure.py` redraws the report figure (needs `matplotlib`).

## What is and isn't here

- **Here:** code to download PeMS files, audit the benchmarks and summarize PeMS provenance.
- **Not here:** PeMS data and the benchmark files. Get them from PeMS (under its terms of use) and from
  the benchmark authors.

## Citation

See [`CITATION.cff`](CITATION.cff).

## License

Code: [Apache-2.0](LICENSE). Report and figure: [CC BY 4.0](report/LICENSE.md).
