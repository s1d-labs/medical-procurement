-- Load the output of hospital_merge.py and map tender links to the active (canonical) HFR ID of each campus.
--   psql -d ws_trideep -v d=DIR -f analysis/hospital_master.sql
drop table if exists medproc.hospital_master cascade;
drop table if exists medproc.hospital_candidate_resolution;
create table medproc.hospital_master (grp int, canonical text, hfr_id text primary key, name text, type text, state text,
  pincode text, km_to_canonical numeric, doctors int, beds int, links int);
create table medproc.hospital_candidate_resolution (corp text, name_word text, tender_mentions int, decision text,
  hfr_id text, reason text, candidates_doctors text);
\set master :d '/master.csv'
\set res :d '/resolution.csv'
copy medproc.hospital_master from :'master' csv header;
copy medproc.hospital_candidate_resolution from :'res' csv header;
-- Bankura Sammilani: the linked stub "Bsmch" (0 doctors, 0 beds, 3 km off) -> the active college ID (76 doctors, 1,441 beds)
update medproc.hospital_master set canonical = 'IN1910011404' where hfr_id = 'IN1910016434';
create view medproc.tender_hospital_canonical as
 select t.corp, t.tender_id, coalesce(m.canonical, t.hfr_id) hfr_id, t.hfr_id hfr_id_linked, t.pool, t.confidence
 from medproc.tender_hospital t left join medproc.hospital_master m on m.hfr_id = t.hfr_id;
