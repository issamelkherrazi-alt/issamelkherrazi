alter table public.profiles
  add column if not exists permissions text[] not null default array[
    'dashboard','clients','commandes','factures','paiements','livraisons',
    'demandes_clients','factures_clients','frais_maroc_clients'
  ]::text[];

drop policy if exists profiles_select on public.profiles;
create policy profiles_select_own_or_admin
on public.profiles for select to authenticated
using (id = (select auth.uid()) or (select private.is_admin()));

comment on column public.profiles.permissions is
  'ERP sections visible and accessible to this employee; admins always have full access.';
