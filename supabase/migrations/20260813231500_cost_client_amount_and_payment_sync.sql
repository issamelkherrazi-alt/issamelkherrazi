alter table public.commandes
  add column if not exists montant_client_rmb numeric default 0;

update public.commandes
set montant_client_rmb = coalesce(montant_container_rmb, 0)
where montant_client_rmb is null or montant_client_rmb = 0;

create or replace function public.sync_commande_merchandise_to_factures()
returns trigger language plpgsql set search_path = ''
as $$
declare v_merch numeric := coalesce(new.montant_client_rmb, 0);
begin
  update public.factures f
  set marchandises_rmb=v_merch,
      commission_rmb=round(v_merch*coalesce(f.commission_pct,0)/100,2),
      montant=round(v_merch+coalesce(f.ocean_freight_rmb,0)+coalesce(f.local_frais_rmb,0)+round(v_merch*coalesce(f.commission_pct,0)/100,2)+coalesce(f.autre_charge_rmb,0)+coalesce(f.frais_coc_rmb,0),2),
      total_usd=case when coalesce(f.exchange_rate,0)>0 then round((v_merch+coalesce(f.ocean_freight_rmb,0)+coalesce(f.local_frais_rmb,0)+round(v_merch*coalesce(f.commission_pct,0)/100,2)+coalesce(f.autre_charge_rmb,0)+coalesce(f.frais_coc_rmb,0))/f.exchange_rate,2) else 0 end,
      reste_rmb=round(v_merch+coalesce(f.ocean_freight_rmb,0)+coalesce(f.local_frais_rmb,0)+round(v_merch*coalesce(f.commission_pct,0)/100,2)+coalesce(f.autre_charge_rmb,0)+coalesce(f.frais_coc_rmb,0)-coalesce(f.recu_rmb,0),2), updated_at=now()
  where f.commande_id=new.id;
  update public.factures_clients fc
  set marchandises_rmb=v_merch,
      commission_rmb=round(v_merch*coalesce(fc.commission_pct,0)/100,2),
      lignes_json=(select coalesce(jsonb_agg(case when coalesce(e.item->>'label','') like 'Total amount des marchandises%' then jsonb_set(e.item,'{amount}',to_jsonb(v_merch),true) when coalesce(e.item->>'label','') like 'Commission%' then jsonb_set(e.item,'{amount}',to_jsonb(round(v_merch*coalesce(fc.commission_pct,0)/100,2)),true) else e.item end order by e.ord),'[]'::jsonb)::text from jsonb_array_elements(case when jsonb_typeof(coalesce(nullif(fc.lignes_json,''),'[]')::jsonb)='array' then coalesce(nullif(fc.lignes_json,''),'[]')::jsonb else '[]'::jsonb end) with ordinality e(item,ord)),
      total_rmb=round(v_merch+coalesce(fc.ocean_freight_rmb,0)+coalesce(fc.local_frais_rmb,0)+round(v_merch*coalesce(fc.commission_pct,0)/100,2)+coalesce(fc.autre_charge_rmb,0)+coalesce(fc.frais_coc_rmb,0),2),
      total_usd=case when coalesce(fc.exchange_rate,0)>0 then round((v_merch+coalesce(fc.ocean_freight_rmb,0)+coalesce(fc.local_frais_rmb,0)+round(v_merch*coalesce(fc.commission_pct,0)/100,2)+coalesce(fc.autre_charge_rmb,0)+coalesce(fc.frais_coc_rmb,0))/fc.exchange_rate,2) else 0 end,
      reste_rmb=round(v_merch+coalesce(fc.ocean_freight_rmb,0)+coalesce(fc.local_frais_rmb,0)+round(v_merch*coalesce(fc.commission_pct,0)/100,2)+coalesce(fc.autre_charge_rmb,0)+coalesce(fc.frais_coc_rmb,0)-coalesce(fc.recu_rmb,0),2), updated_at=now()
  where fc.commande_id=new.id;
  return new;
end;
$$;

drop trigger if exists trg_sync_commande_merchandise_to_factures on public.commandes;
create trigger trg_sync_commande_merchandise_to_factures after update of montant_client_rmb on public.commandes
for each row execute function public.sync_commande_merchandise_to_factures();

create or replace function public.sync_facture_payments_to_client_invoice()
returns trigger language plpgsql set search_path = ''
as $$
begin
  update public.factures_clients fc
  set paiements_json=coalesce(new.paiements_json,'[]'), recu_rmb=coalesce(new.recu_rmb,0),
      reste_rmb=round(coalesce(fc.total_rmb,0)-coalesce(new.recu_rmb,0),2), updated_at=now()
  where fc.commande_id=new.commande_id;
  return new;
end;
$$;

drop trigger if exists trg_sync_facture_payments_to_client_invoice on public.factures;
create trigger trg_sync_facture_payments_to_client_invoice
after insert or update of paiements_json, recu_rmb on public.factures
for each row execute function public.sync_facture_payments_to_client_invoice();
