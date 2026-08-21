alter table public.commandes
  add column if not exists invoice_no text,
  add column if not exists shipper text,
  add column if not exists bl_no text,
  add column if not exists cnt_qty text,
  add column if not exists pol text,
  add column if not exists container_no text,
  add column if not exists vessel_voy text,
  add column if not exists etd date,
  add column if not exists pod text,
  add column if not exists client_ref text;
