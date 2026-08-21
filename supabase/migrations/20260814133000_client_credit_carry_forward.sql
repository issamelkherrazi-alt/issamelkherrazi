alter table public.factures_clients
  add column if not exists credit_applique_rmb numeric not null default 0,
  add column if not exists credit_transfere_rmb numeric not null default 0,
  add column if not exists credit_source_invoice_id bigint references public.factures_clients(id) on delete set null,
  add column if not exists credit_target_invoice_id bigint references public.factures_clients(id) on delete set null;

create index if not exists factures_clients_credit_source_idx
  on public.factures_clients(credit_source_invoice_id);
create index if not exists factures_clients_credit_target_idx
  on public.factures_clients(credit_target_invoice_id);

comment on column public.factures_clients.credit_applique_rmb is 'Credit received automatically from a previous client invoice.';
comment on column public.factures_clients.credit_transfere_rmb is 'Credit transferred automatically to the next client invoice.';
