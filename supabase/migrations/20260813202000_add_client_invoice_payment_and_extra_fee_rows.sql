alter table public.factures_clients
  add column if not exists paiements_json text default '[]',
  add column if not exists autres_frais_json text default '[]';
