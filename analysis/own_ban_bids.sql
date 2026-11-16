-- Bids from firms on the same corporation's whole-firm blacklist, in tenders published inside the ban (17 Nov 2026).
-- Check the bid submission date in the hub record (details.fields.bid_submission_end_date): gepnic "published" can be
-- a re-publication date (2023_RMSCL_318277_1: bids closed Feb 2023, "published" Oct 2026).
create or replace view medproc.own_ban_bids as
 with bans as (
   select distinct case when list like 'tnmsc%' then 'TNMSC' when list like 'rmsc%' then 'RMSCL' when list like 'kmscl%' then 'KMSCL' end corp,
          firm, k, d_from, d_upto, reason
   from medproc.blacklist_periods
   where list in ('tnmsc', 'tnmsc-drug-firm', 'tnmsc-equipment-firm', 'rmsc-company', 'kmscl-drug-firm')),
 b as (
   select b.corp, b.tender_id, b.bidder, b.status, t.published,
          upper(regexp_replace(regexp_replace(b.bidder, '(?i)\m(private|pvt|limited|ltd|m/s)\M', '', 'g'), '[^A-Za-z0-9]', '', 'g')) k
   from medproc.medcorp_bids b join medproc.medcorp_tenders t using (corp, tender_id))
 select bans.corp, bans.firm, bans.d_from, bans.d_upto, bans.reason, b.tender_id, b.bidder, b.published, b.status
 from bans join b on b.corp = bans.corp and b.k = bans.k and b.published between bans.d_from and bans.d_upto;
