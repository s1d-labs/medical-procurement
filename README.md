# medical-procurement

This family scrapes the tenders, notices and documents of the state medical services corporations of India (planned source P17,
with the blacklists of D04). The first site is the West Bengal Medical Services Corporation Ltd. (WBMSC, www.wbmsc.gov.in).
Other corporations (TNMSC, RMSCL, MPPHSCL, HMSCL, BMSICL) are in this repo too; more follow.

## Projects

| Project | Task | Target | What it stores |
|---|---|---|---|
| `medical-procurement-wbmsc` | `wbmsc` | www.wbmsc.gov.in | One record for each row of the tender, notice, award and recruitment lists. One record for each version of each linked document. Raw pages and documents go to the bucket. |
| `medical-procurement-wbmsc-wayback` | `wayback` | web.archive.org | Old versions of the WBMSC pages and documents from the Wayback Machine. |
| `medical-procurement-mpphscl` | `mpphscl` | mpphscl.mp.gov.in | One record for each tender (with all its documents) and each blacklist entry (firm, product, laboratory). One record for each version of each linked document. Raw pages and documents go to the bucket. |
| `medical-procurement-tnmsc` | `tnmsc` | tnmsc.tn.gov.in | Tamil Nadu: blacklists, drug and equipment rate contracts with tenderers and rates, contracts awarded, notifications. The award and notification PDFs go to the bucket. |
| `medical-procurement-rmsc` | `rmsc` | rmsc.health.rajasthan.gov.in | Rajasthan: drug rate contracts, banned firms and products, drug, equipment and finance tenders. The order and tender PDFs go to the bucket. |
| `medical-procurement-hmscl` | `hmscl` | hmscl.org.in | Haryana: drug and equipment rate contracts (item, vendor, rate, validity), banned firms with their order PDFs. |
| `medical-procurement-bmsicl` | `bmsicl` | bmsicl.gov.in | Bihar: rate contract files (drug, reagent, surgical, equipment; one record per row), blacklist posts with their order files. |

## Facts about the MPPHSCL site (2026-11-14)

- The tender list (TenderALL.aspx) is one page of 11.5 MB. It has 1,187 tenders since 2014 and links 13,321 documents.
- The documents include comparative statements, rate lists and final status sheets. These give the bidder, the rate and the rank.
- The three blacklist pages have 140 firms, 236 products and 2 laboratories. Each entry links the order copy.
- The server needs the legacy TLS renegotiation option. The task sets it. Certificate verification stays on.
- The site does not answer GitHub's runners. The project uses an Indian proxy (`proxy="IN"`).
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

## Facts about HMSCL and BMSICL (2026-11-14)

- HMSCL: 428 drug rate contracts and 58 equipment rate contracts (rate without GST, vendor, valid from, valid till). The task reads
  the "Export to Excel" link: it is one HTML table with all rows. The normal page shows 25 rows and ignores `pageSize`.
- HMSCL ban list: 6 firms (2023-2029). Three are for quality failure (NSQ). Tenders and awards are on etenders.hry.nic.in
  (hub project `gepnic-etenders-hry`).
- Use the bare host `hmscl.org.in`. The certificate of `www.hmscl.org.in` is not valid.
- BMSICL answers on HTTP only. The rate contract files are XLSX (2024: 578 drug rows, 84 reagent, 201 surgical, 85 equipment;
  2025: 120 surgical) and one text PDF (2025: 437 drug rows). Other suppliers of a drug have an empty drug cell; the task
  copies the drug from the row above (`alternate_supplier`).
- BMSICL blacklist: 83 drug posts (2018-2026, 9 pages) and 4 equipment posts. Each post links one order file through
  `module_6/download.php`. Most orders are scans (`ocr-needed/`). Product, period and reason are only in the orders.
- Neither site publishes a batch-level NSQ list.

## Facts about TNMSC and RMSC (2026-11-14)

- Each list is one HTML page. There is no pagination. A GET gives the full list. No list needs a sign-in.
- TNMSC blacklist: 93 entries in three tables (drug items 82, drug firms 9, equipment firms 2). 50 entries are for NSQ.
- TNMSC drug rate contracts: 15 tenders, 5,024 drug rows and 3,332 tenderer rows (firm, rate, L1 or matched, order share).
- TNMSC equipment rate contracts: 791 rows in four groups (make, model, rate, valid up to).
- TNMSC contracts awarded: 191 rows (2014, 2015, 2020-2024). The bidders and prices are in the PDFs only.
- TNMSC notifications: 150 rows. On 2026-11-14 the site gave the 2026-27 list for the years 2024-25 and 2025-26 (a site fault).
- RMSC drug rate contracts: 2,070 rows (drug, supplier, rate, level, contract dates).
  The SUPPLIER CONTACT column has names, phones and e-mails of persons. The scraper does not store it.
- RMSC ban lists: 8 debarred firms and 101 banned products. 62 rows give NSQ as the reason. Most order PDFs are scans (`ocr-needed/`).
- RMSC tenders: 1,368 drug, 2,588 equipment and 148 finance rows with about 4,000 PDFs.
- Neither site publishes a list of NSQ batches. The NSQ results show only as the reason of a blacklist or ban entry.
- Neither site answers the GitHub runners (check workflow, 2026-11-14: every request timed out). Both answer from India.
  Both projects use an Indian proxy (`proxy="IN"`). The check workflow cannot test them; use `myproxy run scrape-check`.

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
| `blacklist:<list>:<BL code>:<hash>` | TNMSC: one blacklist entry. |
| `drugrc:<tender>:<drug code>`, `drugrc-bid:<tender>:<drug code>:<firm code>` | TNMSC: one drug of a rate contract, and one tenderer of that drug. |
| `award:CA<n>`, `notification:NF<n>` | TNMSC: one contract awarded, one tender notification (the site's own numbers). |
| `equipmentrc:<hash>` | TNMSC: one equipment rate contract row. A break-up row points to its item (`breakup_of`). |
| `drugrc:<hash>`, `banned-company:<hash>`, `banned-product:<hash>`, `<kind>-tenders:<hash>` | RMSC: one row of a list. |
| `drugrc:<hash>`, `equipmentrc:<hash>`, `banned:<hash>` | HMSCL: one row of a list. |
| `blacklist:<hash>`, `equipment-blacklist:<hash>`, `rcfile:<hash>`, `rc:<hash>` | BMSICL: one blacklist post, one rate contract file link, one row of a rate contract file. |
| `doc:<sha1(url)[:12]>:<sha256[:16]>` | TNMSC, RMSC, HMSCL and BMSICL: one version of a linked file. |

Bucket paths (in the project folder): `pages/<round>/`, `docs/<section>/<sha256>.<ext>`, `text/<sha256>.txt.gz`, and
`ocr-needed/<section>/<sha256>.pdf` for scans with no text layer. OCR is off.

## Run again

To get new tenders and changed documents, change `ROUND` in `family.py`, merge, and run the **setup** workflow.

TNMSC, RMSC, HMSCL and BMSICL have their own pilot sets (`"pilot"` in `corps.py`). After the first pool run looks right, set `"pilot": None`,
merge, and run the **setup** workflow.

## Check

```
pip install -r requirements.txt pytest "scrape-hub-client @ git+https://github.com/s1d-labs/runner@sdk-stable#subdirectory=sdk"
python -m pytest tests -q
scrape-check --items 2
python wbmsc_task.py --local docs tender 0 400 /tmp/out        # one small shard, no hub
python wayback_task.py --local 'wbmsc.gov.in/*' 0 400 /tmp/out
python mpphscl_task.py --local page BlackListFirm.aspx
myproxy run scrape-check --items 2 --project medical-procurement-mpphscl   # India only
python corp_task.py tnmsc --local page blacklist
python corp_task.py rmsc --local docs bans 0 2 /tmp/out
```

The full scraper reference is in `CLAUDE.md`.
