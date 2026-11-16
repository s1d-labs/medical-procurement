-- Facility input for hospital_link.py (psql -d ws_om -At -F, -f analysis/hfr_input.sql > HFR.csv).
-- Columns: hfr_id, hospital, facility_type, ownership, district, state, pincode.
-- 1. government (G) and public-private (PP) hospitals of Om's partial HFR table;
-- 2. government medical colleges of the fuller facility table (the partial table holds only the type "Hospital", so
--    RNT, SSKM, Murshidabad and other medical colleges were missing);
-- 3. Om's reviewed candidates for names missing from the registry (16 Nov 2026): one ID per name, the verified one first.
with base as (
  select hfr_id, hospital, facility_type, ownership, district, state, pincode
  from public.abdm_hfr_india_hospitals_partial where ownership in ('G', 'PP')),
college as (
  select hfr_id, hospital, facility_type, ownership, district, state, pincode
  from public.abdm_hfr_india_facilities
  where ownership = 'G' and facility_type = 'Medical College'
    and hfr_id not in ('IN1910019506', 'IN1910011404')   -- duplicates of Bankura Sammilani (base row IN1910016434 "Bsmch")
    and hfr_id not in (select hfr_id from base)),
cand as (
  select distinct on (c.corp, c.name_word) c.hfr_id, c.facility_name, c.corp, c.name_word
  from public.medproc_missing_hospital_candidates c
  left join public.medproc_verified_hfr_facilities v using (hfr_id)
  left join public.abdm_hfr_india_facilities f using (hfr_id)
  where c.evidence not ilike '%old hospital building%'
    and c.hfr_id not in ('IN1910019506', 'IN1910011404')
  order by c.corp, c.name_word, (v.hfr_id is not null) desc, (f.hfr_id is not null) desc,
           (c.facility_name ilike '%hospital%') desc, c.hfr_id),
reviewed as (
  select distinct on (c.hfr_id) c.hfr_id,
         coalesce(f.hospital, v.hospital, c.facility_name) as hospital,
         coalesce(f.facility_type, v.facility_type,
                  case when c.facility_name ilike '%college%' then 'Medical College' else 'Hospital' end) as facility_type,
         'G' as ownership, coalesce(f.district, v.district, '') as district, r.expected_state as state,
         coalesce(f.pincode, v.pincode, '') as pincode
  from cand c
  join public.medproc_missing_hospital_review r using (corp, name_word)
  left join public.medproc_verified_hfr_facilities v using (hfr_id)
  left join public.abdm_hfr_india_facilities f using (hfr_id)
  where c.hfr_id not in (select hfr_id from base) and c.hfr_id not in (select hfr_id from college))
select hfr_id, '"' || replace(hospital, '"', '') || '"', facility_type, ownership, district, state, pincode from base
union all
select hfr_id, '"' || replace(hospital, '"', '') || '"', facility_type, ownership, district, state, pincode from college
union all
select hfr_id, '"' || replace(hospital, '"', '') || '"', facility_type, ownership, district, state, pincode from reviewed;
