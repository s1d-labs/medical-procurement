-- Rebuild medproc.awards_during_debarment: awards to a firm inside a blacklist period of any corporation.
-- psql -d ws_trideep -f analysis/debarment.sql
-- Firm match: the accepted bidder (status AOC) and the blacklisted firm after removing legal words and non-alphanumerics
-- (medproc.blacklist_periods.k). Product-level lists (tnmsc-drug-item, rmsc-product, kmscl-drug-item) cover one product of
-- the firm: the award can be for another product.
begin;
delete from medproc.awards_during_debarment;
insert into medproc.awards_during_debarment (list, firm, reason, d_from, d_upto, corp, tender_id, published, award_date, title)
with w as (
  select distinct b.corp, b.tender_id, t.published, t.award_date, t.title,
         upper(regexp_replace(regexp_replace(b.bidder, '(?i)\m(private|pvt|limited|ltd|m/s)\M', '', 'g'), '[^A-Za-z0-9]', '', 'g')) k
  from medproc.medcorp_bids b join medproc.medcorp_tenders t using (corp, tender_id)
  where b.status ilike '%AOC%' and t.award_date > '1900-01-01')
select distinct p.list, p.firm, p.reason, p.d_from, p.d_upto, w.corp, w.tender_id, w.published, w.award_date, w.title
from medproc.blacklist_periods p join w on w.k = p.k and w.award_date between p.d_from and p.d_upto;
commit;
