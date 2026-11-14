create temp table orgs(project text, org_id text, corp text);
insert into orgs values
('gepnic-wbtenders','328','WBMSC'),('gepnic-tendersodisha','120','OSMCL'),('gepnic-mptenders','139','MPPHSCL'),('gepnic-etenders-kerala','241','KMSCL'),
('gepnic-etender-up','401','UPMSCL'),('gepnic-etender-up','402','UPMSCL'),('gepnic-tntenders','176','TNMSC'),('gepnic-mahatenders','216','MMGPA'),
('gepnic-jharkhandtenders','89','JMHIDPCL'),('gepnic-eproc-rajasthan','274','RMSCL'),('gepnic-eproc-rajasthan','275','RMSCL'),('gepnic-hptenders','62','HPMSCL'),
('gepnic-mahatenders','172','HAFFKINE');
create temp table r as select o.corp, r.project, r.record_id, r.data from records r join orgs o on r.project=o.project and r.data->>'org_id'=o.org_id
 where r.project in (select project from orgs) and r.data ? 'details';
\copy (select corp, project, coalesce(data->'details'->'fields'->>'tender_id', record_id), f->>'tender_ref_no', f->>'tender_title', f->>'tender_category', f->>'product_category', f->>'form_of_contract', f->>'tender_type', f->>'tender_value', f->>'awarded_value_sum', f->>'l1_bid_value', f->>'winner_bidder_name', f->>'l1_bidder_name', f->>'bids_count', f->>'qualified_bids_count', f->>'priced_bidders', f->>'published_date', f->>'award_date', f->>'location', f->>'pincode', f->>'stage', data->'list'->>'stage' from (select corp, project, record_id, data, data->'details'->'fields' f from r) x) to 'OUT/medcorp_tenders.csv' csv
\copy (select corp, coalesce(data->'details'->'fields'->>'tender_id', record_id), b->>'bidder_name', b->>'status', b->>'remarks', b->>'bid_number', b->>'submitted_date' from r, jsonb_array_elements(coalesce(data->'details'->'bids','[]')) b) to 'OUT/medcorp_bids.csv' csv
\copy (select corp, coalesce(data->'details'->'fields'->>'tender_id', record_id), b->>'bidder', (b->>'value')::numeric, (b->>'rank_num')::int, b->>'rank_raw', b->>'bid_number' from r, jsonb_array_elements(coalesce(data->'details'->'outcomes'->'finance_bid_list','[]')) b) to 'OUT/medcorp_prices.csv' csv
