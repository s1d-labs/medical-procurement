-- Awarded single-winner tenders with 2+ bids where every other bidder was rejected technically ("only one bid reaches
-- the price stage"). Shares on 17 Nov 2026: KMSCL 82 %, TNMSC 70 %, MMGPA 29 %, MPPHSCL 25 %, Haffkine 24 %, RMSCL 21 %,
-- WBMSC 5 %; central benchmark (eprocure.tender_facts, qualified_bids_count = 1): AIIMS 65 %, ESIC 48 %.
create or replace view medproc.tech_narrowing as
 with b as (select corp, tender_id, count(*) n, sum((status ilike '%rejected-tech%')::int) rt, sum((status ilike '%AOC%')::int) aoc
            from medproc.medcorp_bids group by 1, 2)
 select b.corp, b.tender_id, b.n bids, b.rt tech_rejected, t.winner, t.awarded_value, t.published, t.title
 from b join medproc.medcorp_tenders t using (corp, tender_id)
 where b.aoc = 1 and t.awarded_value > 0 and b.n >= 2 and b.rt = b.n - 1;
