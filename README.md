# medical-procurement

This family scrapes the tenders, notices and documents of the state medical services corporations of India (planned source P17,
with the blacklists of D04). The first site is the West Bengal Medical Services Corporation Ltd. (WBMSC, www.wbmsc.gov.in).
Other corporations (TNMSC, RMSCL, GMSCL, KMSCL, BMSICL, MPPHSCL) will follow in this repo.

## Projects

| Project | Task | Target | What it stores |
|---|---|---|---|
| `medical-procurement-wbmsc` | `wbmsc` | www.wbmsc.gov.in | One record for each row of the tender, notice, award and recruitment lists. One record for each version of each linked document. Raw pages and documents go to the bucket. |
| `medical-procurement-wbmsc-wayback` | `wayback` | web.archive.org | Old versions of the WBMSC pages and documents from the Wayback Machine. |
| `medical-procurement-mpphscl` | `mpphscl` | mpphscl.mp.gov.in | One record for each tender (with all its documents) and each blacklist entry (firm, product, laboratory). One record for each version of each linked document. Raw pages and documents go to the bucket. |

## Facts about the MPPHSCL site (2026-11-14)

- The tender list (TenderALL.aspx) is one page of 11.5 MB. It has 1,187 tenders since 2014 and links 13,321 documents.
- The documents include comparative statements, rate lists and final status sheets. These give the bidder, the rate and the rank.
- The three blacklist pages have 140 firms, 236 products and 2 laboratories. Each entry links the order copy.
- The server needs the legacy TLS renegotiation option. The task sets it. Certificate verification stays on.
- The project has no health check, because a standard probe cannot open the site.
- The site has no rate contract list with firm and price. The public "EDL Rate Contract Report" on mpaushadhi.mp.gov.in shows the item, tender and dates only.
- The site has no list of NSQ (not of standard quality) results. The blacklisted products with "Quality Failure" are the nearest list.

## Facts about the WBMSC site (2026-11-14)

- Each list is one page with all rows since 2011. There is no pagination. The tender list has 7,276 rows and links 5,259 files.
- The site gives each new file a random number from 1 to 9999. It reuses a number and overwrites the older file.
  1,586 file names had two or more different tenders. About 2,000 older rows link to a newer, unrelated file.
- The Wayback Machine has copies of 821 of these overwritten files, made before the overwrite.
- The award list has 3 notices, all from 2011. The site does not show who won a tender.
- The site has no robots.txt and no page with terms of use.

## Who won the tenders

The winners are in other projects of the hub. This family does not scrape them again:

- e-tenders on wbtenders.gov.in: project `gepnic-wbtenders` (bidders, bid status, winners);
- GeM bids (`GEM/<year>/B/<number>`): the team database `gem`.

The analysis joins them in the `ws_trideep` database by the NIT number (`nit`) and the GeM bid number (`gem_bid`).

## Records

| Record id | Meaning |
|---|---|
| `tender:<hash>`, `notice:<hash>`, `award:<hash>`, `recruitment:<hash>` | A row of a list. The hash is of the row text and link, not of the file name. |
| `doc:<section>/<file>:<sha256[:16]>` | One version of a linked file. A new version gets a new record. |
| `missing:<section>/<file>:<round>` | A link that did not give the file. |
| `page:<round>:<page>` | One snapshot of a page. |
| `wb:<path>:<digest[:16]>` | One archived content from the Wayback Machine, with all its capture times. |

Bucket paths (in the project folder): `pages/<round>/`, `docs/<section>/<sha256>.<ext>`, `text/<sha256>.txt.gz`, and
`ocr-needed/<section>/<sha256>.pdf` for scans with no text layer. OCR is off.

## Run again

To get new tenders and changed documents, change `ROUND` in `family.py`, merge, and run the **setup** workflow.

## Check

```
pip install -r requirements.txt pytest "scrape-hub-client @ git+https://github.com/s1d-labs/runner@sdk-stable#subdirectory=sdk"
python -m pytest tests -q
scrape-check --items 2
python wbmsc_task.py --local docs tender 0 400 /tmp/out        # one small shard, no hub
python wayback_task.py --local 'wbmsc.gov.in/*' 0 400 /tmp/out
python mpphscl_task.py --local page BlackListFirm.aspx
scrape-check --items 2 --project medical-procurement-mpphscl
```

The full scraper reference is in `CLAUDE.md`.
