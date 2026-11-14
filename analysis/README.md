# Analysis scripts

These scripts make the analysis tables in the `ws_trideep` database (schema `medproc`). They run in a team box. They are not part of the pool tasks.

| Script | What it makes |
|---|---|
| `medcorp_export.sql` | CSV files of the e-tenders, bids and financial bids of 11 state medical corporations, from the `gepnic-*` projects in `scrape_hub`. Replace `OUT/` with a folder, run it with `psql -d scrape_hub -f`, then load the files into `medproc.medcorp_tenders_raw`, `medproc.medcorp_bids` and `medproc.medcorp_prices`. |
| `wayback_removed.py` | Rows of the WBMSC tender and notice lists in Wayback copies that are not in the current lists. Run `python3 -I analysis/wayback_removed.py PAGES_DIR OUT.csv`, then load the file into `medproc.wbmsc_removed_rows`. |

The organisation ids of the corporations come from the `gepnic-*-plan` projects. The script does not copy the names of officials ("Updated By" fields).
