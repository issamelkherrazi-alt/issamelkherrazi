alter table public.factures
  add column if not exists autres_charges_json text not null default '[]';
