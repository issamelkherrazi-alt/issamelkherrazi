alter table public.factures_clients
  add column if not exists marchandises_rmb numeric default 0,
  add column if not exists exchange_rate numeric default 0,
  add column if not exists ocean_freight_usd numeric default 0,
  add column if not exists ocean_freight_rmb numeric default 0,
  add column if not exists local_frais_rmb numeric default 0,
  add column if not exists commission_pct numeric default 0,
  add column if not exists commission_rmb numeric default 0,
  add column if not exists autre_charge_rmb numeric default 0,
  add column if not exists frais_coc_rmb numeric default 0,
  add column if not exists note_charge text;

update public.factures_clients f
set marchandises_rmb = coalesce(c.montant_container_rmb, 0),
    exchange_rate = coalesce(c.exchange_rate, 0),
    ocean_freight_usd = coalesce(c.ocean_freight_usd, 0),
    ocean_freight_rmb = coalesce(c.ocean_freight_rmb, 0),
    local_frais_rmb = coalesce(c.local_frais_rmb, 0),
    commission_pct = coalesce(c.commission_pct, 0),
    commission_rmb = coalesce(c.commission_rmb, 0),
    autre_charge_rmb = coalesce(c.autre_charge_rmb, 0),
    note_charge = c.note_charge
from public.commandes c
where f.commande_id = c.id and coalesce(f.marchandises_rmb, 0) = 0;

grant select, insert, update on public.factures_clients to authenticated;
