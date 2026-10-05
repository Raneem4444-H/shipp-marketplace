-- Shipp - Supabase setup. Run once in Supabase: SQL Editor -> New query -> Run.
-- Creates the three tables the pipeline reads, following the Lakebase ERD.
-- Skip this file if your tables already exist (then just check the names in CONFIG).

create table if not exists public.users (
  user_id      text primary key,
  name         text not null,
  current_city text,
  created_at   timestamptz not null default now()
);

create table if not exists public.listings (
  listing_id      text primary key,
  donor_id        text not null references public.users (user_id),
  title           text not null,
  description     text,
  category        text not null,
  condition       text,
  location        text,
  latitude        double precision,
  longitude       double precision,
  available_from  date,
  available_until date,
  status          text not null default 'Available',
  updated_at      timestamptz not null default now()
);

create table if not exists public.requests (
  request_id   text primary key,
  requester_id text not null references public.users (user_id),
  request_text text,
  category     text not null,
  location     text,
  latitude     double precision,
  longitude    double precision,
  need_by_date date,
  status       text not null default 'Open',
  updated_at   timestamptz not null default now()
);

-- Row-level security ON with no policies: the publishable key can read nothing,
-- the secret key (used by the pipeline) can read everything.
alter table public.users    enable row level security;
alter table public.listings enable row level security;
alter table public.requests enable row level security;

-- ---------------------------------------------------------------------------
-- Seed rows (SYNTHETIC, for the first end-to-end run). Safe to re-run.
-- Coordinates are approximate district centres - replace with your own city.
-- ---------------------------------------------------------------------------
insert into public.users (user_id, name, current_city) values
  ('u_001', 'Seed Donor One',     'Dubai'),
  ('u_002', 'Seed Donor Two',     'Dubai'),
  ('u_003', 'Seed Requester One', 'Dubai'),
  ('u_004', 'Seed Requester Two', 'Dubai')
on conflict (user_id) do nothing;

insert into public.listings
  (listing_id, donor_id, title, description, category, condition, location,
   latitude, longitude, available_from, available_until, status)
values
  ('l_001', 'u_001', 'Three-seat sofa', 'Grey fabric sofa, two years old, no stains.',
   'furniture', 'good', 'Dubai Marina', 25.0805, 55.1403, '2026-10-01', '2026-11-15', 'Available'),
  ('l_002', 'u_001', 'Dining table with four chairs', 'Solid wood, minor scratches on one leg.',
   'furniture', 'fair', 'Dubai Marina', 25.0805, 55.1403, '2026-10-05', '2026-11-30', 'Available'),
  ('l_003', 'u_002', 'Floor lamp', 'Brass floor lamp with a white shade.',
   'home-decoration', 'like_new', 'Business Bay', 25.1850, 55.2650, '2026-10-01', '2026-10-31', 'Available'),
  ('l_004', 'u_002', 'Microwave oven', '20 litre microwave, works perfectly.',
   'kitchen-accessories', 'good', 'Business Bay', 25.1850, 55.2650, '2026-10-03', '2026-11-10', 'Available')
on conflict (listing_id) do nothing;

insert into public.requests
  (request_id, requester_id, request_text, category, location,
   latitude, longitude, need_by_date, status)
values
  ('r_001', 'u_003', 'Need a sofa for a new one-bedroom flat.',
   'furniture', 'Al Barsha', 25.1107, 55.2000, '2026-10-25', 'Open'),
  ('r_002', 'u_004', 'Looking for a microwave or other kitchen basics.',
   'kitchen-accessories', 'Deira', 25.2711, 55.3075, '2026-10-20', 'Open'),
  ('r_003', 'u_004', 'Any lamps or small decor for the living room.',
   'home-decoration', 'Deira', 25.2711, 55.3075, '2026-11-05', 'Open')
on conflict (request_id) do nothing;
