alter table public.clients
  add column if not exists consignee text,
  add column if not exists address text,
  add column if not exists ice text;

alter table public.commandes
  add column if not exists consignee text,
  add column if not exists address text,
  add column if not exists telephone text,
  add column if not exists ice text;

update public.commandes as c
set consignee = upper(coalesce(cl.consignee, '')),
    address = upper(coalesce(cl.address, '')),
    telephone = upper(coalesce(cl.telephone, '')),
    ice = upper(coalesce(cl.ice, ''))
from public.clients as cl
where c.client = cl.nom;
