-- SHIPP — Supabase intake tables read by notebooks/ingestion/05_supabase_live_intake.py
-- Run once in Supabase: SQL Editor -> New query -> Run. Safe to re-run.

create table if not exists public.donor_intake (
  external_listing_id text primary key,
  donor_id            text not null,
  title               text not null,
  description         text,
  category            text not null,
  condition           text not null,
  location            text not null,
  latitude            double precision not null,
  longitude           double precision not null,
  available_until     date not null,
  created_at          timestamptz not null default now()
);

create table if not exists public.requester_intake (
  external_request_id text primary key,
  requester_id        text not null,
  request_text        text not null,
  category            text not null,
  location            text not null,
  latitude            double precision not null,
  longitude           double precision not null,
  need_by_date        date not null,
  created_at          timestamptz not null default now()
);

-- Row-level security ON with no policies:
-- the publishable key reads nothing, the secret key (used by the pipeline) reads everything.
alter table public.donor_intake     enable row level security;
alter table public.requester_intake enable row level security;

-- Synthetic seed rows. The notebook's final gate checks for these two IDs.
-- Category must be one of: FURNITURE, KITCHEN, ELECTRONICS, BOOKS, CLOTHING, OTHER
-- Condition must be one of: NEW, LIKE_NEW, GOOD, FAIR, USED
insert into public.donor_intake
  (external_listing_id, donor_id, title, description, category, condition,
   location, latitude, longitude, available_until)
values
  ('live-listing-001', 'live-donor-001', 'Solid wood dining table',
   'Six-seat wooden dining table, minor scratches on one leg.',
   'FURNITURE', 'GOOD', 'Dubai Marina', 25.0805, 55.1403, '2026-11-30')
on conflict (external_listing_id) do nothing;

insert into public.requester_intake
  (external_request_id, requester_id, request_text, category,
   location, latitude, longitude, need_by_date)
values
  ('live-request-001', 'live-requester-001',
   'Need a dining table for a new family apartment.',
   'FURNITURE', 'Al Barsha', 25.1107, 55.2000, '2026-11-15')
on conflict (external_request_id) do nothing;

-- Check
select 'donor_intake' as table_name, count(*) from public.donor_intake
union all
select 'requester_intake', count(*) from public.requester_intake;
