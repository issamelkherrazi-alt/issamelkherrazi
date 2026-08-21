import os
import json
import re
from functools import wraps
from io import BytesIO
from datetime import date
from xml.sax.saxutils import escape
from flask import Flask, flash, redirect, render_template, request, url_for, send_file, session, g
from supabase import create_client
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-in-production")

@app.after_request
def disable_asset_cache(response):
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://wnreasruwfwsndzpswxq.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_jvdINlC7yb3K3ANng1I7RQ_VKGGDdE4")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "issamelkherrazi@gmail.com").lower()

PERMISSION_LABELS = {
    "dashboard": "Tableau de bord",
    "clients": "Clients",
    "commandes": "Commandes",
    "factures": "Factures",
    "demandes_clients": "Demandes Clients",
    "factures_clients": "Factures Clients",
    "frais_maroc_clients": "Frais Maroc Clients",
}
DEFAULT_EMPLOYEE_PERMISSIONS = list(PERMISSION_LABELS)

TABLES = {
    "clients": {
        "title": "Clients", "icon": "👥", "pk": "id",
        "fields": [("nom", "Nom client", "text"), ("consignee", "CONSIGNEE", "uppercase"),
                   ("address", "ADDRESS", "uppercase"), ("telephone", "TELEPHONE", "uppercase"),
                   ("ice", "ICE", "uppercase"),
                   ("email", "E-mail", "email"), ("ville", "Ville", "text"),
                   ("marchandises", "Type de marchandises", "text"),
                   ("bon_payeur", "Paie correctement ?", "select:Oui,Non,Variable"),
                   ("statut", "Statut", "select:Actif,À relancer,Inactif"), ("notes", "Notes", "textarea")]
    },
    "commandes": {
        "title": "Commandes", "icon": "📦", "pk": "id",
        "fields": [("client", "Client", "client"), ("client_ref", "Réf Client", "uppercase"),
                   ("invoice_no", "N° facture automatique", "text"),
                   ("consignee", "CONSIGNEE", "client_info"),
                   ("address", "ADDRESS", "client_info"), ("telephone", "TELEPHONE", "client_info"),
                   ("ice", "ICE", "client_info"), ("produit", "Produit / Marchandise", "text"),
                   ("type_container", "Type container", "select:20GP (FCL),40GP (FCL),40HQ (FCL),45HQ (FCL),LCL (Groupage)"),
                   ("fournisseur", "Fournisseur", "suppliers"),
                   ("shipper", "Shipper", "suppliers"),
                   ("date_commande", "Date", "date"),
                   ("statut", "Statut", "select:Devis,Confirmée,En production,Expédiée,Livrée,Annulée"),
                   ("booking", "Booking", "select:Confirmé,En cours,Non"),
                   ("compagnie_maritime", "Compagnie maritime", "calculated_text"),
                   ("booking_no", "N° Booking", "calculated_text"),
                   ("agent_maritime", "Agent maritime", "calculated_text"),
                   ("booking_date", "Date Booking", "date"),
                   ("montant_container_rmb", "Coût des marchandises (RMB)", "number"),
                   ("montant_client_rmb", "Montant client des marchandises (RMB)", "number"),
                   ("coc", "COC", "select:Non requis,À faire,En cours,Validé,Bloqué"),
                   ("bl_no", "B/L No", "text"), ("container_no", "Container No", "text")]
    },
    "factures": {
        "title": "Factures", "icon": "🧾", "pk": "id",
        "fields": [("commande_id", "N° commande", "command"), ("numero", "N° facture", "auto_text"),
                   ("client", "Client", "auto_client"),
                   ("type", "Type", "select:Proforma,Commerciale,Acompte,Solde"),
                   ("marchandises_rmb", "Total amount des marchandises (RMB)", "calculated"),
                   ("ocean_freight_usd", "Ocean Freight (USD)", "number"),
                   ("exchange_rate", "Exchange USD → RMB", "number"),
                   ("ocean_freight_rmb", "Ocean Freight converti (RMB)", "calculated"),
                   ("agent_maritime", "Agent maritime", "calculated_text"),
                   ("local_frais_rmb", "Local Frais (RMB)", "number"),
                   ("commission_pct", "Commission (%)", "number"),
                   ("commission_rmb", "Commission calculée (RMB)", "calculated"),
                   ("autres_charges_json", "Autres charges (RMB)", "extra_charges"),
                   ("frais_coc_rmb", "Frais COC (RMB)", "number"),
                   ("note_charge", "Note de charge", "textarea"),
                   ("montant", "Total facture (RMB)", "calculated"),
                   ("total_usd", "Total facture (USD)", "calculated"),
                   ("paiements_json", "Paiements reçus", "payments"),
                   ("recu_rmb", "Reçu Payment total (RMB)", "calculated"),
                   ("reste_rmb", "Rest Need to Pay (RMB)", "calculated"),
                   ("devise", "Devise", "select:RMB,USD,DHS"),
                   ("date_facture", "Date", "date"), ("envoyee", "Envoyée", "select:Oui,Non"),
                   ("comptable", "Comptable", "select:Oui,Non")]
    },
    "demandes_clients": {
        "title": "Demandes Clients", "icon": "📌", "pk": "id",
        "fields": [("client", "Client", "client"), ("commande_id", "Commande liée", "optional_command"),
                   ("demande", "Demande du client", "textarea"),
                   ("date_demande", "Date de la demande", "date"),
                   ("date_echeance", "Date limite / Rappel", "date"),
                   ("priorite", "Priorité", "select:Normale,Haute,Urgente"),
                   ("statut", "Confirmation / Statut", "select:À confirmer,Confirmée,En cours,Terminée,Annulée"),
                   ("notes", "Notes de suivi", "textarea")]
    }
}

ZH = {
    "Clients":"客户", "Commandes":"订单", "Factures":"发票", "Livraisons & COC":"运输与COC", "Demandes Clients":"客户需求",
    "Responsable":"负责人", "N° dossier":"档案号", "N° dépôt":"申请号", "Organisme COC":"COC机构",
    "Situation COC":"COC状态", "Type d’inspection":"检验类型", "Statut inspection":"检验状态", "Date inspection":"检验日期",
    "Date de dépôt":"申请日期", "Exportateur":"出口商", "Identifiant plateforme":"平台账号", "Paiement COC":"COC付款状态",
    "Test Report":"测试报告", "Coût COC":"COC费用", "Coût Test Report":"测试报告费用", "Devise des coûts":"费用币种",
    "Total COC + Test Report":"COC及测试报告总费用", "Remarque COC":"COC备注",
    "Nom client":"客户名称", "Téléphone":"电话", "TELEPHONE":"电话", "CONSIGNEE":"收货人", "ADDRESS":"地址", "ICE":"统一企业识别码", "E-mail":"邮箱", "Ville":"城市", "Type de marchandises":"货物类型",
    "Paie correctement ?":"付款信誉", "Statut":"状态", "Notes":"备注", "Client":"客户", "Produit / Marchandise":"产品/货物",
    "Type container":"集装箱类型", "Fournisseur":"供应商", "Date":"日期", "Booking":"订舱",
    "Coût des marchandises (RMB)":"成本", "Montant client des marchandises (RMB)":"客户货物金额",
    "Réf Client":"客户简称", "N° facture automatique":"自动发票号", "N° facture":"发票号",
    "Client / Bill To":"客户/收货方", "Invoice No":"发票号", "CNT QTY":"柜量", "Shipper":"发货人",
    "B/L No":"提单号", "Container No":"集装箱号", "POL":"装货港", "POD":"卸货港",
    "Vessel / Voyage":"船名/航次", "ETD":"预计离港", "Client Ref":"客户参考号",
    "Ocean Freight (USD)":"海运费（美元）", "Exchange USD → RMB":"美元兑人民币汇率", "Ocean Freight converti (RMB)":"海运费折合人民币",
    "Montant global container (RMB)":"货柜总金额（人民币）", "Local Frais (RMB)":"本地费用（人民币）",
    "Commission (%)":"佣金比例", "Commission calculée (RMB)":"佣金金额（人民币）", "Autre charge (RMB)":"其他费用（人民币）",
    "Note de charge":"费用备注", "Total automatique (RMB)":"自动合计（人民币）", "Total automatique (USD)":"自动合计（美元）",
    "Paiements reçus":"收款记录", "Reçu Payment total (RMB)":"已收款合计（人民币）", "Rest Need to Pay (RMB)":"待付余额（人民币）",
    "COC":"COC认证", "N° commande":"订单号", "Type":"类型", "Montant":"金额", "Devise":"币种", "Envoyée":"已发送",
    "Comptable":"会计", "Montant dû":"应付金额", "Reçu":"已收金额", "Échéance":"到期日", "Référence":"参考号",
    "Port départ":"起运港", "Destination":"目的地", "ETA":"预计到达", "Container":"集装箱",
    "Actif":"活跃", "À relancer":"需跟进", "Inactif":"停用", "Oui":"是", "Non":"否", "Variable":"不稳定",
    "Devis":"报价", "Confirmée":"已确认", "En production":"生产中", "Expédiée":"已发货", "Livrée":"已交付", "Annulée":"已取消",
    "Confirmé":"已确认", "En cours":"进行中", "Non requis":"不需要", "À faire":"待处理", "Validé":"已通过", "Bloqué":"受阻",
    "En attente":"等待中", "Partiel":"部分", "Payé":"已付款", "En retard":"逾期", "Préparation":"准备中", "En transit":"运输中", "Arrivée":"已到达",
    "Rechercher":"搜索", "Rechercher...":"搜索…", "+ Nouveau":"+ 新建", "Modifier":"修改", "Supprimer":"删除", "Actions":"操作",
    "Nouveau":"新建", "Remplissez les informations ci-dessous":"请填写以下信息", "— Choisir —":"— 请选择 —",
    "— Choisir un client —":"— 请选择客户 —", "+ Ajouter un paiement":"+ 添加付款", "Montant RMB":"人民币金额",
    "MA · Maroc":"MA · 摩洛哥", "CN · Chine":"CN · 中国", "Annuler":"取消", "Enregistrer":"保存",
    "Tableau de bord":"仪表盘", "Vue générale de votre activité":"业务概览", "Urgences":"紧急事项",
    "Dernières commandes":"最近订单", "+ Ajouter":"+ 添加", "Voir les dossiers →":"查看记录 →",
    "Commande liée":"关联订单", "Demande du client":"客户需求", "Date de la demande":"需求日期",
    "Date limite / Rappel":"截止/提醒日期", "Priorité":"优先级", "Confirmation / Statut":"确认/状态", "Notes de suivi":"跟进备注"
}

@app.template_filter("zh")
def chinese(value):
    return ZH.get(str(value), str(value))

@app.context_processor
def bilingual_context():
    return {"zh_map": ZH, "current_user": session.get("user"),
            "is_admin": session.get("role") == "admin", "user_permissions": session.get("permissions", []),
            "permission_labels": PERMISSION_LABELS}

def has_permission(section):
    return session.get("role") == "admin" or section in session.get("permissions", [])

def first_allowed_url():
    if has_permission("dashboard"): return url_for("dashboard")
    for section in ("clients", "commandes", "factures", "demandes_clients"):
        if has_permission(section): return url_for("listing", table=section)
    if has_permission("factures_clients"): return url_for("client_invoices")
    if has_permission("frais_maroc_clients"): return url_for("morocco_fees")
    return url_for("no_access")

def deny_unless(section):
    if has_permission(section): return None
    flash("Vous n’avez pas accès à cette section.", "error")
    return redirect(first_allowed_url())

def supabase_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Configuration Supabase manquante")
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    if session.get("access_token") and session.get("refresh_token"):
        auth = client.auth.set_session(session["access_token"], session["refresh_token"])
        if auth.session:
            session["access_token"] = auth.session.access_token
            session["refresh_token"] = auth.session.refresh_token
    return client

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("access_token"):
            return redirect(url_for("login", next=request.path))
        try:
            g.supabase = supabase_client()
        except Exception:
            session.clear()
            flash("Votre session a expiré. Reconnectez-vous.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def fetch_one(table, item_id):
    if item_id in (None, ""):
        return None
    rows = g.supabase.table(table).select("*").eq("id", item_id).limit(1).execute().data
    return rows[0] if rows else None

def annotate_command_numbers(commands):
    """Add a safe per-client display number without changing database primary keys."""
    counters = {}
    for command in sorted(commands, key=lambda row: (str(row.get("date_commande") or "9999-12-31"), int(row.get("id") or 0))):
        client_key = str(command.get("client") or "").strip().casefold()
        counters[client_key] = counters.get(client_key, 0) + 1
        command["_client_order_no"] = counters[client_key]
    return commands

def command_number_map(commands):
    annotate_command_numbers(commands)
    return {str(command.get("id")): command.get("_client_order_no") for command in commands}

def payment_amount_rmb(payment):
    try:
        amount=float(payment.get("amount") or 0);rate=float(payment.get("rate") or 0);currency=payment.get("currency") or "RMB"
        return amount if currency=="RMB" else (amount/rate if currency=="DHS" and rate else amount*rate)
    except (TypeError,ValueError,AttributeError):
        return 0

def safe_number(value):
    try: return float(value or 0)
    except (TypeError, ValueError): return 0

def json_charge_total(value):
    """Total flexible charge rows saved by Factures or Factures Clients."""
    try: rows = json.loads(value or "[]")
    except (TypeError, ValueError): rows = []
    if not isinstance(rows, list): return 0
    total = 0
    for row in rows:
        if isinstance(row, dict): total += safe_number(row.get("amount"))
    return round(total, 2)

def json_charge_map(value):
    try: rows = json.loads(value or "[]")
    except (TypeError, ValueError): rows = []
    result = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict): continue
        label = str(row.get("remark") or row.get("label") or "Autre frais").strip() or "Autre frais"
        key = re.sub(r"\s+", " ", label).casefold()
        result[key] = {"label":label, "amount":round(result.get(key, {}).get("amount", 0) + safe_number(row.get("amount")), 2)}
    return result

def rebuild_client_credit_chain(client_name):
    """Rebuild invoice payments and carried credit from the authoritative Factures rows."""
    client_name=str(client_name or "").strip()
    if not client_name:return
    invoices=g.supabase.table("factures_clients").select("*").eq("client",client_name).execute().data
    if not invoices:return
    commands=g.supabase.table("commandes").select("id,date_commande").eq("client",client_name).execute().data
    command_dates={str(command.get("id")):str(command.get("date_commande") or "9999-12-31") for command in commands}
    invoices.sort(key=lambda invoice:(command_dates.get(str(invoice.get("commande_id")),"9999-12-31"),int(invoice.get("id") or 0)))
    facture_rows=g.supabase.table("factures").select("id,commande_id,montant,paiements_json,recu_rmb,reste_rmb").order("id",desc=True).execute().data
    facture_by_command={}
    for facture in facture_rows:
        key=str(facture.get("commande_id"))
        if key not in facture_by_command:facture_by_command[key]=facture
    incoming=0;source=None
    for invoice in invoices:
        facture=facture_by_command.get(str(invoice.get("commande_id")))
        raw=(facture or {}).get("paiements_json") or invoice.get("paiements_json") or "[]"
        try:parsed=json.loads(raw);parsed=parsed if isinstance(parsed,list) else []
        except (TypeError,ValueError):parsed=[]
        own=[p for p in parsed if not isinstance(p,dict) or p.get("type")!="credit_transfer"]
        # Legacy invoices sometimes recorded the carried credit as an ordinary RMB payment.
        legacy_credit=float(invoice.get("credit_applique_rmb") or 0)
        if legacy_credit>0 and not any(isinstance(p,dict) and p.get("type")=="credit_transfer" for p in parsed):
            removed=False;clean=[]
            for p in own:
                if not removed and isinstance(p,dict) and (p.get("currency") or "RMB")=="RMB" and abs(payment_amount_rmb(p)-legacy_credit)<0.01:
                    removed=True;continue
                clean.append(p)
            own=clean
        payments=list(own);source_id=None;source_numero=None
        if incoming>0 and source:
            source_id=source.get("id");source_numero=source.get("numero")
            payments.append({"type":"credit_transfer","amount":round(incoming,2),"currency":"RMB","rate":1,
                             "date":invoice.get("date_facture") or date.today().isoformat(),"place":"Solde antérieur",
                             "source_invoice_id":source_id,"source_numero":source_numero})
        received=round(sum(payment_amount_rmb(p) for p in payments),2)
        total=float(invoice.get("total_rmb") or 0);balance=round(total-received,2)
        update={"paiements_json":json.dumps(payments,ensure_ascii=False),"recu_rmb":received,"reste_rmb":balance,
                "credit_applique_rmb":round(incoming,2),"credit_source_invoice_id":source_id,
                "credit_transfere_rmb":0,"credit_target_invoice_id":None}
        g.supabase.table("factures_clients").update(update).eq("id",invoice["id"]).execute()
        if facture:
            facture_total=float(facture.get("montant") or total)
            g.supabase.table("factures").update({"paiements_json":update["paiements_json"],"recu_rmb":received,
                                                  "reste_rmb":round(facture_total-received,2)}).eq("id",facture["id"]).execute()
        if incoming>0 and source:
            g.supabase.table("factures_clients").update({"credit_transfere_rmb":round(incoming,2),
                                                          "credit_target_invoice_id":invoice["id"]}).eq("id",source["id"]).execute()
        incoming=max(-balance,0);source=invoice if incoming>0 else None

def annotate_display_ids(rows):
    """Consecutive visible IDs: deleting one record automatically closes the gap."""
    sequence = {str(row.get("id")): index for index, row in enumerate(sorted(rows, key=lambda item: int(item.get("id") or 0)), 1)}
    for row in rows:
        row["_display_id"] = sequence.get(str(row.get("id")))
    return rows

def automatic_invoice_number(command):
    """Build REF-YEARNn from the client reference and per-client command number."""
    prefix = re.sub(r"[^A-Z0-9]+", "", str(command.get("client_ref") or "FC").upper()) or "FC"
    year = str(command.get("date_commande") or date.today().isoformat())[:4]
    return f"{prefix}-{year}N{int(command.get('_client_order_no') or 1)}"

def sync_auto_invoice_numbers(user_id):
    """Keep command, supplier invoice and client invoice numbers aligned."""
    commands = g.supabase.table("commandes").select("id,client,client_ref,date_commande,invoice_no").order("date_commande").order("id").execute().data
    annotate_command_numbers(commands)
    for command in commands:
        # Keep a manually edited command invoice number. Generate one only when empty.
        numero = str(command.get("invoice_no") or "").strip() or automatic_invoice_number(command)
        if not str(command.get("invoice_no") or "").strip():
            g.supabase.table("commandes").update({"invoice_no": numero, "updated_by": user_id}).eq("id", command["id"]).execute()
        # Supplier and client invoices always follow the command number.
        g.supabase.table("factures").update({"numero": numero, "updated_by": user_id}).eq("commande_id", command["id"]).execute()
        g.supabase.table("factures_clients").update({"numero": numero, "updated_by": user_id}).eq("commande_id", command["id"]).execute()

def clean_form_values(cfg):
    values = {}
    for name, _label, field_type in cfg["fields"]:
        raw = request.form.get(name, "").strip()
        if field_type in ("number", "calculated"):
            values[name] = float(raw) if raw else None
        elif field_type in ("calculated_text", "auto_text"):
            values[name] = raw
        elif field_type in ("command", "optional_command"):
            values[name] = int(raw) if raw else None
        elif field_type == "date":
            values[name] = raw or None
        elif field_type in ("uppercase", "client_info"):
            values[name] = raw.upper()
        else:
            values[name] = raw
    return values

def sync_command_merchandise(command_id, merchandise, user_id):
    """Recalculate every linked supplier and client invoice after an order amount changes."""
    def number(value):
        try: return float(value or 0)
        except (TypeError, ValueError): return 0
    def json_list(value):
        try:
            parsed = json.loads(value or "[]")
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError): return []

    supplier_invoices = g.supabase.table("factures").select("*").eq("commande_id", command_id).execute().data
    for invoice in supplier_invoices:
        commission = round(merchandise * number(invoice.get("commission_pct")) / 100, 2)
        total = round(merchandise + number(invoice.get("ocean_freight_rmb")) + number(invoice.get("local_frais_rmb")) + commission + number(invoice.get("autre_charge_rmb")) + number(invoice.get("frais_coc_rmb")), 2)
        rate = number(invoice.get("exchange_rate")); received = number(invoice.get("recu_rmb"))
        update = {"marchandises_rmb": merchandise, "commission_rmb": commission, "montant": total,
                  "total_usd": round(total / rate, 2) if rate else 0, "reste_rmb": round(total - received, 2),
                  "updated_by": user_id}
        g.supabase.table("factures").update(update).eq("id", invoice["id"]).execute()

    client_invoices = g.supabase.table("factures_clients").select("*").eq("commande_id", command_id).execute().data
    for invoice in client_invoices:
        commission = round(merchandise * number(invoice.get("commission_pct")) / 100, 2)
        lines = json_list(invoice.get("lignes_json"))
        found_merchandise = found_commission = False
        for line in lines:
            if not isinstance(line, dict): continue
            label = str(line.get("label") or "")
            if label.startswith("Total amount des marchandises"):
                line["amount"] = merchandise; found_merchandise = True
            elif label.startswith("Commission"):
                line["amount"] = commission; found_commission = True
        if not found_merchandise: lines.insert(0, {"label": "Total amount des marchandises", "amount": merchandise})
        if not found_commission: lines.append({"label": "Commission RMB", "amount": commission})
        total = round(sum(number(line.get("amount")) for line in lines if isinstance(line, dict)), 2)
        rate = number(invoice.get("exchange_rate")); received = number(invoice.get("recu_rmb"))
        update = {"marchandises_rmb": merchandise, "commission_rmb": commission,
                  "lignes_json": json.dumps(lines, ensure_ascii=False), "total_rmb": total,
                  "total_usd": round(total / rate, 2) if rate else 0, "reste_rmb": round(total - received, 2),
                  "updated_by": user_id}
        g.supabase.table("factures_clients").update(update).eq("id", invoice["id"]).execute()

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            client = create_client(SUPABASE_URL, SUPABASE_KEY)
            auth = client.auth.sign_in_with_password({"email": request.form.get("email", "").strip(), "password": request.form.get("password", "")})
            profile = client.table("profiles").select("full_name,role,permissions").eq("id", auth.user.id).single().execute().data
            permissions = profile.get("permissions")
            if permissions is None:
                permissions = DEFAULT_EMPLOYEE_PERMISSIONS
            session.clear()
            session.update(access_token=auth.session.access_token, refresh_token=auth.session.refresh_token,
                           user={"id": str(auth.user.id), "email": auth.user.email, "name": profile.get("full_name") or auth.user.email},
                           role=profile.get("role", "employee"), permissions=permissions)
            target = request.args.get("next")
            return redirect(target if target and target.startswith("/") else first_allowed_url())
        except Exception:
            flash("E-mail ou mot de passe incorrect.", "error")
    return render_template("login.html")

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    sent = False
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if email:
            try:
                client = create_client(SUPABASE_URL, SUPABASE_KEY)
                reset_url = url_for("reset_password", _external=True, _scheme="https" if request.is_secure else "http")
                client.auth.reset_password_for_email(email, {"redirect_to": reset_url})
            except Exception:
                pass
        sent = True
    return render_template("forgot_password.html", sent=sent, admin_email=ADMIN_EMAIL)

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    success = False
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        access_token = request.form.get("access_token", "")
        refresh_token = request.form.get("refresh_token", "")
        if len(password) < 8:
            error = "Le mot de passe doit contenir au moins 8 caractères."
        elif password != confirmation:
            error = "Les deux mots de passe ne correspondent pas."
        elif not access_token or not refresh_token:
            error = "Lien invalide ou expiré. Demandez un nouveau lien."
        else:
            try:
                client = create_client(SUPABASE_URL, SUPABASE_KEY)
                client.auth.set_session(access_token, refresh_token)
                client.auth.update_user({"password": password})
                success = True
            except Exception:
                error = "Impossible de modifier le mot de passe. Demandez un nouveau lien."
    return render_template("reset_password.html", success=success, error=error)

@app.route("/register-admin", methods=["GET", "POST"])
def register_admin():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if email != ADMIN_EMAIL:
            flash(f"Le premier compte Admin doit utiliser {ADMIN_EMAIL}.", "error")
        elif len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.", "error")
        elif password != confirmation:
            flash("Les deux mots de passe ne correspondent pas.", "error")
        else:
            try:
                client = create_client(SUPABASE_URL, SUPABASE_KEY)
                auth = client.auth.sign_up({"email": email, "password": password, "options": {"data": {"full_name": "Admin ISA"}}})
                if auth.session:
                    profile = client.table("profiles").select("full_name,role").eq("id", auth.user.id).single().execute().data
                    session.clear()
                    session.update(access_token=auth.session.access_token, refresh_token=auth.session.refresh_token,
                                   user={"id": str(auth.user.id), "email": auth.user.email, "name": profile.get("full_name") or auth.user.email}, role=profile.get("role", "admin"))
                    return redirect(url_for("dashboard"))
                flash("Compte créé. Vérifiez votre e-mail pour confirmer le compte, puis connectez-vous.", "ok")
                return redirect(url_for("login"))
            except Exception as exc:
                message = str(exc).lower()
                if "already" in message or "registered" in message:
                    flash("Ce compte existe déjà. Connectez-vous ou utilisez « mot de passe oublié ».", "error")
                else:
                    flash("Impossible de créer le compte. Vérifiez l’e-mail et réessayez.", "error")
    return render_template("register_admin.html", admin_email=ADMIN_EMAIL)

@app.post("/logout")
def logout():
    try:
        supabase_client().auth.sign_out()
    except Exception:
        pass
    session.clear()
    return redirect(url_for("login"))

@app.route("/no-access")
@login_required
def no_access():
    return render_template("no_access.html", tables=TABLES), 403

@app.route("/employes", methods=["GET", "POST"])
@login_required
def employees():
    if session.get("role") != "admin":
        flash("Gestion des employés réservée à l’administrateur.", "error")
        return redirect(first_allowed_url())
    if request.method == "POST":
        action = request.form.get("action")
        permissions = [key for key in PERMISSION_LABELS if key in request.form.getlist("permissions")]
        try:
            if action == "create":
                email = request.form.get("email", "").strip().lower()
                full_name = request.form.get("full_name", "").strip()
                password = request.form.get("password", "")
                if not email or len(password) < 8:
                    raise ValueError("E-mail obligatoire et mot de passe de 8 caractères minimum.")
                signup_client = create_client(SUPABASE_URL, SUPABASE_KEY)
                auth = signup_client.auth.sign_up({"email": email, "password": password,
                                                   "options": {"data": {"full_name": full_name}}})
                if not auth.user:
                    raise ValueError("Compte non créé.")
                g.supabase.table("profiles").update({"full_name": full_name, "permissions": permissions}).eq("id", str(auth.user.id)).execute()
                flash("Compte employé créé. Le collègue doit confirmer le lien reçu par e-mail avant la première connexion.", "ok")
            elif action == "update":
                profile_id = request.form.get("profile_id", "")
                full_name = request.form.get("full_name", "").strip()
                g.supabase.table("profiles").update({"full_name": full_name, "permissions": permissions}).eq("id", profile_id).eq("role", "employee").execute()
                flash("Permissions de l’employé mises à jour. Elles s’appliqueront à sa prochaine connexion.", "ok")
            elif action == "resend":
                email = request.form.get("email", "").strip().lower()
                if not email:
                    raise ValueError("E-mail employé introuvable.")
                confirmation_url = url_for("login", _external=True, _scheme="https" if request.is_secure else "http")
                resend_client = create_client(SUPABASE_URL, SUPABASE_KEY)
                resend_client.auth.resend({"type": "signup", "email": email,
                                           "options": {"email_redirect_to": confirmation_url}})
                flash(f"Lien d’activation renvoyé à {email}. Vérifiez aussi le dossier Spam.", "ok")
        except Exception as exc:
            message = str(exc)
            if "already" in message.lower() or "registered" in message.lower():
                message = "Cet e-mail possède déjà un compte."
            flash(message or "Opération impossible.", "error")
        return redirect(url_for("employees"))
    rows = g.supabase.table("profiles").select("id,email,full_name,role,permissions,created_at").order("created_at").execute().data
    return render_template("employees.html", employees=[row for row in rows if row.get("role") != "admin"],
                           permission_labels=PERMISSION_LABELS, tables=TABLES)

@app.template_filter("money")
def money(v):
    try: return f"{float(v):,.2f}"
    except (TypeError, ValueError): return v or "—"

@app.template_filter("amount_due")
def amount_due(v):
    try: return max(float(v or 0), 0)
    except (TypeError, ValueError): return 0

@app.template_filter("client_credit")
def client_credit(v):
    try: return max(-float(v or 0), 0)
    except (TypeError, ValueError): return 0

@app.template_filter("available_credit")
def available_credit(row):
    try:
        return max(-float(row.get("reste_rmb") or 0) - float(row.get("credit_transfere_rmb") or 0), 0)
    except (TypeError, ValueError, AttributeError):
        return 0

def command_ids_with_ocean_freight(*row_groups):
    """Return commandes already carrying Ocean Freight in either invoice side."""
    command_ids = set()
    for rows in row_groups:
        for row in rows or []:
            try:
                has_freight = float(row.get("ocean_freight_usd") or 0) > 0 or float(row.get("ocean_freight_rmb") or 0) > 0
            except (TypeError, ValueError, AttributeError):
                has_freight = False
            if has_freight and row.get("commande_id") is not None:
                command_ids.add(str(row.get("commande_id")))
    return command_ids

@app.route("/")
@login_required
def dashboard():
    denied = deny_unless("dashboard")
    if denied: return denied
    today = date.today().isoformat()
    data = {t: g.supabase.table(t).select("*").execute().data for t in TABLES}
    client_invoice_balances = g.supabase.table("factures_clients").select("id,numero,commande_id,client,reste_rmb,paiements_json,ocean_freight_usd,ocean_freight_rmb").execute().data
    morocco_fee_rows = g.supabase.table("frais_maroc_clients").select("total_dhs").execute().data
    morocco_fee_total = round(sum(float(row.get("total_dhs") or 0) for row in morocco_fee_rows), 2)
    total_reste_rmb = round(sum(max(float(row.get("reste_rmb") or 0), 0) for row in client_invoice_balances), 2)
    unpaid_invoices = sum(1 for row in client_invoice_balances if float(row.get("reste_rmb") or 0) > 0)
    commands_by_id = {str(row.get("id")): row for row in data["commandes"]}
    client_last_payments = {}
    for invoice in client_invoice_balances:
        client = (invoice.get("client") or "Client sans nom").strip()
        try:
            invoice_payments = json.loads(invoice.get("paiements_json") or "[]")
        except (TypeError, ValueError):
            invoice_payments = []
        payment_dates = [str(payment.get("date")) for payment in invoice_payments
                         if isinstance(payment, dict) and payment.get("date")
                         and payment.get("type") != "credit_transfer"]
        if payment_dates:
            latest = max(payment_dates)
            if latest > client_last_payments.get(client, ""):
                client_last_payments[client] = latest
    client_dues_map = {}
    for row in client_invoice_balances:
        due = max(float(row.get("reste_rmb") or 0), 0)
        if due <= 0:
            continue
        client = (row.get("client") or "Client sans nom").strip()
        item = client_dues_map.setdefault(client, {"client": client, "amount": 0, "invoices": 0, "details": []})
        item["amount"] += due
        item["invoices"] += 1
        command = commands_by_id.get(str(row.get("commande_id")), {})
        last_payment_date = client_last_payments.get(client)
        loading_date = command.get("date_commande")
        days_since_loading = None
        if loading_date:
            try:
                days_since_loading = max((date.today() - date.fromisoformat(str(loading_date)[:10])).days, 0)
            except ValueError:
                pass
        item["details"].append({
            "invoice": row.get("numero") or f"#{row.get('id')}",
            "bl_no": command.get("bl_no") or "—",
            "container_no": command.get("container_no") or "—",
            "loading_date": loading_date,
            "days_since_loading": days_since_loading,
            "last_payment_date": last_payment_date,
            "amount": round(due, 2),
        })
    client_dues = sorted(client_dues_map.values(), key=lambda item: item["amount"], reverse=True)
    for item in client_dues:
        item["amount"] = round(item["amount"], 2)
        item["details"].sort(key=lambda detail: detail.get("loading_date") or "", reverse=True)
    counts = {t: len(rows) for t, rows in data.items()}
    urgences = []
    checks = [
        ("Clients à relancer", "clients", lambda r: r.get("statut") == "À relancer"),
        ("Devis en attente", "commandes", lambda r: r.get("statut") == "Devis"),
        ("Factures non envoyées", "factures", lambda r: r.get("envoyee") == "Non"),
        ("Demandes clients à confirmer", "demandes_clients", lambda r: r.get("statut") == "À confirmer"),
        ("Demandes clients en retard", "demandes_clients", lambda r: r.get("date_echeance") and r["date_echeance"] < today and r.get("statut") not in ("Terminée", "Annulée"))]
    for label, table, check in checks:
        n = sum(1 for row in data[table] if check(row))
        if n:
            urgences.append({"label": label, "count": n, "table": table})
    urgences = sorted(urgences, key=lambda x: x["count"], reverse=True)[:5]
    annotate_command_numbers(data["commandes"])
    recent = sorted(data["commandes"], key=lambda r: r["id"], reverse=True)
    supplier_by_command = {}
    for invoice in sorted(data["factures"], key=lambda row: row.get("id") or 0, reverse=True):
        key = str(invoice.get("commande_id"))
        if key not in supplier_by_command: supplier_by_command[key] = invoice
    client_by_command = {}
    for invoice in sorted(client_invoice_balances, key=lambda row: row.get("id") or 0, reverse=True):
        key = str(invoice.get("commande_id"))
        if key not in client_by_command: client_by_command[key] = invoice
    dossier_pipeline = []
    for command in recent:
        key = str(command.get("id")); supplier_invoice = supplier_by_command.get(key); client_invoice = client_by_command.get(key)
        if not supplier_invoice:
            stage = "missing_supplier"; stage_label = "Facture à créer"
        elif not client_invoice:
            stage = "missing_client"; stage_label = "Facture client à créer"
        else:
            stage = "complete"; stage_label = "Dossier facturé"
        dossier_pipeline.append({"command": command, "supplier_invoice": supplier_invoice,
                                 "client_invoice": client_invoice, "stage": stage, "stage_label": stage_label})
    # Priority display: dossiers needing action first, completed dossiers last.
    stage_priority = {"missing_supplier": 0, "missing_client": 1, "complete": 2}
    dossier_pipeline.sort(key=lambda row: (stage_priority.get(row["stage"], 99), -(row["command"].get("id") or 0)))
    pipeline_counts = {
        "missing_supplier": sum(1 for row in dossier_pipeline if row["stage"] == "missing_supplier"),
        "missing_client": sum(1 for row in dossier_pipeline if row["stage"] == "missing_client"),
        "complete": sum(1 for row in dossier_pipeline if row["stage"] == "complete"),
    }
    container_clients = {}
    all_containers = set()
    for command in data["commandes"]:
        container = str(command.get("container_no") or "").strip().upper()
        if not container: continue
        client = str(command.get("client") or "Client sans nom").strip() or "Client sans nom"
        all_containers.add(container)
        item = container_clients.setdefault(client, {"client":client, "containers":set()})
        item["containers"].add(container)
    container_stats = []
    for item in container_clients.values():
        numbers = sorted(item["containers"])
        container_stats.append({"client":item["client"], "count":len(numbers), "containers":numbers})
    container_stats.sort(key=lambda item:(-item["count"], item["client"].casefold()))
    return render_template("dashboard.html", counts=counts, urgences=urgences, recent=recent, tables=TABLES,
                           total_reste_rmb=total_reste_rmb, unpaid_invoices=unpaid_invoices,
                           client_dues=client_dues,
                           dossier_pipeline=dossier_pipeline, pipeline_counts=pipeline_counts,
                           total_containers=len(all_containers), container_stats=container_stats,
                           morocco_fee_count=len(morocco_fee_rows), morocco_fee_total=morocco_fee_total)

@app.route("/<table>")
def listing(table):
    if not session.get("access_token"): return redirect(url_for("login"))
    try: g.supabase = supabase_client()
    except Exception: session.clear(); return redirect(url_for("login"))
    if table not in TABLES: return redirect(url_for("dashboard"))
    denied = deny_unless(table)
    if denied: return denied
    q = request.args.get("q", "").strip(); cfg = TABLES[table]
    query = g.supabase.table(table).select("*")
    if q:
        cols = [f[0] for f in cfg["fields"] if f[2] not in ("number", "calculated", "date", "payments", "extra_charges", "command", "optional_command")]
        query = query.or_(",".join(f"{c}.ilike.%{q}%" for c in cols))
    rows = query.order("id", desc=True).execute().data
    annotate_display_ids(rows)
    if table == "commandes":
        commands_all = g.supabase.table("commandes").select("id,client,date_commande").order("date_commande").order("id").execute().data
        numbers = command_number_map(commands_all)
        for row in rows:
            row["_display_id"] = numbers.get(str(row.get("id")), row.get("id"))
    if any(field[0] == "commande_id" for field in cfg["fields"]):
        commands_all = g.supabase.table("commandes").select("id,client,date_commande").order("date_commande").order("id").execute().data
        numbers = command_number_map(commands_all)
        for row in rows: row["_commande_no"] = numbers.get(str(row.get("commande_id")), row.get("commande_id"))
    facture_groups = []
    if table == "factures":
        grouped = {}
        for row in rows:
            client = str(row.get("client") or "Client sans nom").strip() or "Client sans nom"
            group = grouped.setdefault(client, {"client": client, "rows": [], "count": 0, "total": 0.0, "recu": 0.0, "reste": 0.0})
            group["rows"].append(row); group["count"] += 1
            group["total"] += safe_number(row.get("montant"))
            group["recu"] += safe_number(row.get("recu_rmb"))
            group["reste"] += max(safe_number(row.get("reste_rmb")), 0)
        facture_groups = list(grouped.values())
        for group in facture_groups:
            for key in ("total", "recu", "reste"): group[key] = round(group[key], 2)
    return render_template("list.html", table=table, cfg=cfg, rows=rows, q=q, tables=TABLES, facture_groups=facture_groups)

@app.route("/<table>/new", methods=["GET", "POST"])
@app.route("/<table>/<int:item_id>/edit", methods=["GET", "POST"])
def edit(table, item_id=None):
    if not session.get("access_token"): return redirect(url_for("login"))
    try: g.supabase = supabase_client()
    except Exception: session.clear(); return redirect(url_for("login"))
    if table not in TABLES: return redirect(url_for("dashboard"))
    denied = deny_unless(table)
    if denied: return denied
    cfg = TABLES[table]; row = fetch_one(table, item_id) if item_id else None
    if not row and table == "factures" and request.args.get("commande_id"):
        row = {"commande_id": request.args.get("commande_id")}
    clients = g.supabase.table("clients").select("id,nom,consignee,address,telephone,ice").order("nom").execute().data
    commands = g.supabase.table("commandes").select("*").order("id", desc=True).execute().data
    annotate_command_numbers(commands)
    if request.method == "POST":
        values = clean_form_values(cfg)
        if table == "demandes_clients":
            values["date_demande"] = values.get("date_demande") or date.today().isoformat()
            values["priorite"] = values.get("priorite") or "Normale"
            values["statut"] = values.get("statut") or "À confirmer"
        if table == "factures":
            command = fetch_one("commandes", values.get("commande_id"))
            if not command:
                flash("Choisissez un numéro de commande valide.", "error")
                return render_template("form.html", table=table, cfg=cfg, row=values, clients=clients, commands=commands, tables=TABLES), 400
            def amount(name):
                try: return float(values.get(name) or 0)
                except (TypeError, ValueError): return 0
            merchandise = float(command.get("montant_client_rmb") or command.get("montant_container_rmb") or 0)
            if not values.get("ocean_freight_usd") and command.get("ocean_freight_usd"):
                values["ocean_freight_usd"] = command.get("ocean_freight_usd")
            if not values.get("exchange_rate") and command.get("exchange_rate"):
                values["exchange_rate"] = command.get("exchange_rate")
            values["agent_maritime"] = values.get("agent_maritime") or command.get("agent_maritime") or ""
            rate = amount("exchange_rate")
            freight_rmb = round(amount("ocean_freight_usd") * rate, 2)
            commission = round(merchandise * amount("commission_pct") / 100, 2)
            try: extra_charge_rows = json.loads(values.get("autres_charges_json") or "[]")
            except (TypeError, ValueError): extra_charge_rows = []
            normalized_charges = []
            extra_charge_total = 0
            for charge in extra_charge_rows if isinstance(extra_charge_rows, list) else []:
                if not isinstance(charge, dict): continue
                try: charge_amount = float(charge.get("amount") or 0)
                except (TypeError, ValueError): charge_amount = 0
                remark = str(charge.get("remark") or charge.get("label") or "Autre charge").strip() or "Autre charge"
                normalized_charges.append({"remark": remark, "amount": charge_amount})
                extra_charge_total += charge_amount
            extra_charge_total = round(extra_charge_total, 2)
            total = round(merchandise + freight_rmb + amount("local_frais_rmb") + commission + extra_charge_total + amount("frais_coc_rmb"), 2)
            try: payment_rows = json.loads(values.get("paiements_json") or "[]")
            except (TypeError, ValueError): payment_rows = []
            payment_rows = payment_rows if isinstance(payment_rows, list) else []
            recu = 0
            for payment in payment_rows:
                if isinstance(payment, dict):
                    try:
                        payment_amount=float(payment.get("amount") or 0); payment_rate=float(payment.get("rate") or 0); currency=payment.get("currency", "RMB")
                        recu += payment_amount if currency == "RMB" else (payment_amount / payment_rate if currency == "DHS" and payment_rate else payment_amount * payment_rate)
                    except (TypeError, ValueError): pass
            recu = round(recu, 2)
            commands_numbered = g.supabase.table("commandes").select("id,client,client_ref,date_commande").order("id").execute().data
            annotate_command_numbers(commands_numbered)
            numbered_command = next((c for c in commands_numbered if str(c.get("id")) == str(command.get("id"))), command)
            values.update(numero=(command.get("invoice_no") or automatic_invoice_number(numbered_command)), client=command.get("client") or "", marchandises_rmb=merchandise,
                          ocean_freight_rmb=freight_rmb, commission_rmb=commission, montant=total,
                          autres_charges_json=json.dumps(normalized_charges, ensure_ascii=False), autre_charge_rmb=extra_charge_total,
                          total_usd=round(total / rate, 2) if rate else 0, paiements_json=json.dumps(payment_rows, ensure_ascii=False),
                          recu_rmb=recu, reste_rmb=round(total - recu, 2), devise=values.get("devise") or "RMB")
        if table == "commandes":
            client_row = next((client for client in clients if client.get("nom") == values.get("client")), None)
            if client_row:
                for field in ("consignee", "address", "telephone", "ice"):
                    values[field] = str(client_row.get(field) or "").upper()
        if table == "livraisons":
            command = fetch_one("commandes", values.get("commande_id"))
            if command:
                values["client"] = command.get("client") or ""
                values["container"] = values.get("container") or command.get("container_no") or ""
            values["cout_coc"] = float(values.get("cout_coc") or 0)
            values["cout_test_rapport"] = float(values.get("cout_test_rapport") or 0)
            values["total_coc"] = round(values["cout_coc"] + values["cout_test_rapport"], 2)
            values["devise_coc"] = values.get("devise_coc") or "RMB"
        try:
            if item_id:
                values["updated_by"] = session["user"]["id"]
                g.supabase.table(table).update(values).eq("id", item_id).execute()
            else:
                values.update(created_by=session["user"]["id"], updated_by=session["user"]["id"])
                g.supabase.table(table).insert(values).execute()
            if table == "clients" and item_id and row:
                client_snapshot = {field: values.get(field) or "" for field in ("consignee", "address", "telephone", "ice")}
                client_snapshot["client"] = values.get("nom") or row.get("nom")
                client_snapshot["updated_by"] = session["user"]["id"]
                g.supabase.table("commandes").update(client_snapshot).eq("client", row.get("nom")).execute()
            if table == "commandes" and item_id:
                sync_command_merchandise(item_id, float(values.get("montant_client_rmb") or 0), session["user"]["id"])
            if table == "commandes":
                sync_auto_invoice_numbers(session["user"]["id"])
            if table == "factures":
                rebuild_client_credit_chain(values.get("client") or (command or {}).get("client"))
        except Exception:
            flash("Enregistrement impossible. Vérifiez les champs obligatoires et les montants.", "error")
            return render_template("form.html", table=table, cfg=cfg, row=values, clients=clients, commands=commands, tables=TABLES), 400
        flash("Enregistrement sauvegardé.", "ok"); return redirect(url_for("listing", table=table))
    return render_template("form.html", table=table, cfg=cfg, row=row, clients=clients, commands=commands, tables=TABLES)

def recalculate_supplier_invoice(invoice, freight_usd, rate, agent, user_id):
    freight_rmb = round(float(freight_usd or 0) * float(rate or 0), 2)
    merchandise = float(invoice.get("marchandises_rmb") or 0)
    local = float(invoice.get("local_frais_rmb") or 0)
    commission = float(invoice.get("commission_rmb") or 0)
    coc = float(invoice.get("frais_coc_rmb") or 0)
    try: charges = json.loads(invoice.get("autres_charges_json") or "[]")
    except (TypeError, ValueError): charges = []
    extras = sum(float(x.get("amount") or 0) for x in charges if isinstance(x, dict))
    total = round(merchandise + freight_rmb + local + commission + coc + extras, 2)
    received = float(invoice.get("recu_rmb") or 0)
    return {"ocean_freight_usd": float(freight_usd or 0), "exchange_rate": float(rate or 0),
            "ocean_freight_rmb": freight_rmb, "agent_maritime": agent or "", "montant": total,
            "total_usd": round(total / float(rate), 2) if float(rate or 0) else 0,
            "reste_rmb": round(total - received, 2), "updated_by": user_id}

@app.route("/factures-clients")
def client_invoices():
    if not session.get("access_token"): return redirect(url_for("login"))
    try: g.supabase = supabase_client()
    except Exception: session.clear(); return redirect(url_for("login"))
    denied = deny_unless("factures_clients")
    if denied: return denied
    rows=g.supabase.table("factures_clients").select("*").order("id", desc=True).execute().data
    annotate_display_ids(rows)
    commands_all=g.supabase.table("commandes").select("id,client,date_commande").order("date_commande").order("id").execute().data
    numbers=command_number_map(commands_all)
    for row in rows: row["_commande_no"]=numbers.get(str(row.get("commande_id")),row.get("commande_id"))
    invoice_map={str(row.get("id")):row for row in rows}
    for row in rows:
        source=invoice_map.get(str(row.get("credit_source_invoice_id")))
        target=invoice_map.get(str(row.get("credit_target_invoice_id")))
        row["_credit_source_numero"]=(source or {}).get("numero")
        row["_credit_target_numero"]=(target or {}).get("numero")
    q=request.args.get("q", "").strip()
    if q:
        needle=q.casefold().lstrip("#")
        rows=[row for row in rows if needle in str(row.get("numero") or "").casefold() or needle in str(row.get("client") or "").casefold() or needle == str(row.get("commande_id") or "").casefold()]
    grouped = {}
    for row in rows:
        client = str(row.get("client") or "Client sans nom").strip() or "Client sans nom"
        group = grouped.setdefault(client, {"client":client, "rows":[], "count":0, "total":0.0, "recu":0.0, "reste":0.0, "solde":0.0})
        group["rows"].append(row); group["count"] += 1
        group["total"] += safe_number(row.get("total_rmb"))
        group["recu"] += safe_number(row.get("recu_rmb"))
        group["reste"] += max(safe_number(row.get("reste_rmb")), 0)
        group["solde"] += max(-safe_number(row.get("reste_rmb")) - safe_number(row.get("credit_transfere_rmb")), 0)
    client_groups = list(grouped.values())
    for group in client_groups:
        for key in ("total","recu","reste","solde"): group[key] = round(group[key],2)
    return render_template("client_invoices.html",rows=rows,groups=client_groups,q=q,tables=TABLES)

@app.route("/benefices-commissions")
def profits_commissions():
    """Admin-only automatic comparison of real costs and amounts billed to clients."""
    if not session.get("access_token"): return redirect(url_for("login"))
    try: g.supabase = supabase_client()
    except Exception: session.clear(); return redirect(url_for("login"))
    if session.get("role") != "admin":
        return render_template("no_access.html", tables=TABLES), 403

    commands = g.supabase.table("commandes").select("*").order("date_commande", desc=True).order("id", desc=True).execute().data
    annotate_command_numbers(commands)
    supplier_rows = g.supabase.table("factures").select("*").order("id", desc=True).execute().data
    client_rows = g.supabase.table("factures_clients").select("*").order("id", desc=True).execute().data
    supplier_by_command = {}; client_by_command = {}
    for invoice in supplier_rows:
        key = str(invoice.get("commande_id"))
        if key not in supplier_by_command: supplier_by_command[key] = invoice
    for invoice in client_rows:
        key = str(invoice.get("commande_id"))
        if key not in client_by_command: client_by_command[key] = invoice

    rows = []
    for command in commands:
        key = str(command.get("id")); cost_invoice = supplier_by_command.get(key); billed_invoice = client_by_command.get(key)
        cost = cost_invoice or {}; billed = billed_invoice or {}
        cost_merchandise = safe_number(command.get("montant_container_rmb"))
        billed_merchandise = safe_number(command.get("montant_client_rmb"))
        if not billed_merchandise: billed_merchandise = safe_number(billed.get("marchandises_rmb")) or cost_merchandise
        cost_extras = json_charge_map(cost.get("autres_charges_json")); billed_extras = json_charge_map(billed.get("autres_frais_json"))
        if not cost_extras and safe_number(cost.get("autre_charge_rmb")): cost_extras["autre charge"] = {"label":"Autre charge", "amount":safe_number(cost.get("autre_charge_rmb"))}
        if not billed_extras and safe_number(billed.get("autre_charge_rmb")): billed_extras["autre charge"] = {"label":"Autre charge", "amount":safe_number(billed.get("autre_charge_rmb"))}
        details = [
            {"label":"Marchandises", "cost":cost_merchandise, "billed":billed_merchandise},
            {"label":"Ocean Freight", "cost":safe_number(cost.get("ocean_freight_rmb")), "billed":safe_number(billed.get("ocean_freight_rmb"))},
            {"label":"Local Frais", "cost":safe_number(cost.get("local_frais_rmb")), "billed":safe_number(billed.get("local_frais_rmb"))},
            {"label":"Commission", "cost":safe_number(cost.get("commission_rmb")), "billed":safe_number(billed.get("commission_rmb"))},
            {"label":"Frais COC", "cost":safe_number(cost.get("frais_coc_rmb")), "billed":safe_number(billed.get("frais_coc_rmb"))},
        ]
        for extra_key in sorted(set(cost_extras) | set(billed_extras)):
            details.append({"label":(billed_extras.get(extra_key) or cost_extras.get(extra_key))["label"],
                            "cost":(cost_extras.get(extra_key) or {}).get("amount",0),
                            "billed":(billed_extras.get(extra_key) or {}).get("amount",0)})
        for detail in details: detail["difference"] = round(detail["billed"] - detail["cost"], 2)
        cost_total = round(sum(item["cost"] for item in details), 2)
        billed_total = round(sum(item["billed"] for item in details), 2)
        profit = round(billed_total - cost_total, 2)
        rows.append({"command":command, "cost_invoice":cost_invoice, "client_invoice":billed_invoice,
                     "details":details, "cost_total":cost_total, "billed_total":billed_total,
                     "commission":safe_number(billed.get("commission_rmb")), "profit":profit,
                     "is_complete":bool(cost_invoice and billed_invoice)})

    q = request.args.get("q", "").strip(); needle = q.casefold().lstrip("#")
    status = request.args.get("status", "all")
    current_year = date.today().year
    years = list(range(2025, current_year + 1))
    selected_year = request.args.get("year", "all").strip()
    if selected_year != "all":
        try:
            year_int = int(selected_year)
            rows = [row for row in rows if str(row["command"].get("date_commande") or "")[:4] == str(year_int)]
        except (TypeError, ValueError):
            selected_year = "all"
    if needle:
        rows = [row for row in rows if any(needle in str(value or "").casefold() for value in
                (row["command"].get("client"), row["command"].get("container_no"), row["command"].get("bl_no"),
                 row["command"].get("invoice_no"), row["command"].get("_client_order_no")))]
    if status == "complete": rows = [row for row in rows if row["cost_invoice"] and row["client_invoice"]]
    elif status == "missing": rows = [row for row in rows if not row["cost_invoice"] or not row["client_invoice"]]
    complete_rows = [row for row in rows if row["is_complete"]]
    totals = {"cost":round(sum(row["cost_total"] for row in complete_rows),2),
              "billed":round(sum(row["billed_total"] for row in complete_rows),2),
              "commission":round(sum(row["commission"] for row in complete_rows),2),
              "profit":round(sum(row["profit"] for row in complete_rows),2),
              "complete":len(complete_rows)}
    grouped = {}
    for row in rows:
        client = str(row["command"].get("client") or "Client sans nom").strip() or "Client sans nom"
        group = grouped.setdefault(client, {"client":client,"rows":[],"count":0,"complete":0,"cost":0.0,"billed":0.0,"commission":0.0,"profit":0.0})
        group["rows"].append(row); group["count"] += 1
        if row["is_complete"]:
            group["complete"] += 1
            group["cost"] += row["cost_total"]; group["billed"] += row["billed_total"]
            group["commission"] += row["commission"]; group["profit"] += row["profit"]
    profit_groups = list(grouped.values())
    for group in profit_groups:
        for key in ("cost","billed","commission","profit"): group[key] = round(group[key],2)
    return render_template("profits_commissions.html", rows=rows, groups=profit_groups, totals=totals, q=q, status=status, years=years, selected_year=selected_year, tables=TABLES)

@app.post("/<table>/bulk-delete")
def bulk_delete(table):
    if not session.get("access_token"):
        return redirect(url_for("login"))
    try:
        g.supabase = supabase_client()
    except Exception:
        session.clear()
        return redirect(url_for("login"))
    denied = deny_unless(table)
    if denied:
        return denied
    if session.get("role") != "admin":
        flash("Suppression réservée à l’administrateur.", "error")
        return redirect(url_for("listing", table=table))
    if table not in ("commandes", "factures"):
        flash("Suppression multiple non disponible pour cette section.", "error")
        return redirect(url_for("listing", table=table))
    raw_ids = request.form.getlist("selected_ids")
    ids = []
    for value in raw_ids:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            pass
    ids = sorted(set(ids))
    if not ids:
        flash("Sélectionnez au moins un dossier.", "error")
        return redirect(url_for("listing", table=table))
    try:
        g.supabase.table(table).delete().in_("id", ids).execute()
        if table == "commandes":
            sync_auto_invoice_numbers(session["user"]["id"])
        flash(f"{len(ids)} dossier(s) supprimé(s).", "ok")
    except Exception:
        flash("Suppression multiple impossible.", "error")
    return redirect(url_for("listing", table=table))

@app.post("/<table>/<int:item_id>/delete")
def delete(table, item_id):
    if not session.get("access_token"):
        return redirect(url_for("login"))
    try:
        g.supabase = supabase_client()
    except Exception:
        session.clear()
        return redirect(url_for("login"))
    denied = deny_unless(table)
    if denied:
        return denied
    if session.get("role") != "admin":
        flash("Suppression réservée à l’administrateur.", "error")
        return redirect(url_for("listing", table=table))
    if table in TABLES:
        g.supabase.table(table).delete().eq("id", item_id).execute()
        if table == "commandes":
            sync_auto_invoice_numbers(session["user"]["id"])
        flash("Enregistrement supprimé.", "ok")
    return redirect(url_for("listing", table=table))

@app.post("/factures-clients/bulk-delete")
def client_invoices_bulk_delete():
    if not session.get("access_token"):
        return redirect(url_for("login"))
    try:
        g.supabase = supabase_client()
    except Exception:
        session.clear()
        return redirect(url_for("login"))
    denied = deny_unless("factures_clients")
    if denied: return denied
    if session.get("role") != "admin":
        flash("Suppression réservée à l’administrateur.", "error")
        return redirect(url_for("client_invoices"))
    ids=[]
    for value in request.form.getlist("selected_ids"):
        try: ids.append(int(value))
        except (TypeError, ValueError): pass
    ids=sorted(set(ids))
    if not ids:
        flash("Sélectionnez au moins une facture client.", "error")
        return redirect(url_for("client_invoices"))
    deleted=0
    try:
        # Apply the same credit-transfer cleanup as individual deletion.
        for invoice_id in ids:
            invoice=fetch_one("factures_clients", invoice_id)
            if not invoice: continue
            source_id=invoice.get("credit_source_invoice_id"); applied=float(invoice.get("credit_applique_rmb") or 0)
            if source_id and applied and int(source_id) not in ids:
                source=fetch_one("factures_clients",source_id)
                if source:g.supabase.table("factures_clients").update({"credit_transfere_rmb":max(float(source.get("credit_transfere_rmb") or 0)-applied,0),"credit_target_invoice_id":None}).eq("id",source_id).execute()
            target_id=invoice.get("credit_target_invoice_id"); transferred=float(invoice.get("credit_transfere_rmb") or 0)
            if target_id and transferred and int(target_id) not in ids:
                target=fetch_one("factures_clients",target_id)
                if target:
                    try: target_payments=json.loads(target.get("paiements_json") or "[]")
                    except (TypeError,ValueError): target_payments=[]
                    target_payments=[p for p in target_payments if not isinstance(p,dict) or not (p.get("type")=="credit_transfer" and str(p.get("source_invoice_id"))==str(invoice_id))]
                    target_recu=round(float(target.get("recu_rmb") or 0)-transferred,2)
                    g.supabase.table("factures_clients").update({"paiements_json":json.dumps(target_payments,ensure_ascii=False),"recu_rmb":target_recu,"reste_rmb":round(float(target.get("total_rmb") or 0)-target_recu,2),"credit_applique_rmb":0,"credit_source_invoice_id":None}).eq("id",target_id).execute()
            g.supabase.table("factures_clients").delete().eq("id",invoice_id).execute()
            deleted += 1
        flash(f"{deleted} facture(s) client supprimée(s).", "ok")
    except Exception:
        flash("Suppression multiple impossible.", "error")
    return redirect(url_for("client_invoices"))

@app.post("/factures-clients/<int:invoice_id>/delete")
def client_invoice_delete(invoice_id):
    if not session.get("access_token"):
        return redirect(url_for("login"))
    try:
        g.supabase = supabase_client()
    except Exception:
        session.clear()
        return redirect(url_for("login"))
    denied = deny_unless("factures_clients")
    if denied: return denied
    if session.get("role") != "admin":
        flash("Suppression réservée à l’administrateur.", "error")
        return redirect(url_for("client_invoices"))
    invoice = fetch_one("factures_clients", invoice_id)
    if not invoice:
        flash("Facture client introuvable.", "error")
        return redirect(url_for("client_invoices"))
    try:
        source_id=invoice.get("credit_source_invoice_id");applied=float(invoice.get("credit_applique_rmb") or 0)
        if source_id and applied:
            source=fetch_one("factures_clients",source_id)
            if source:g.supabase.table("factures_clients").update({"credit_transfere_rmb":max(float(source.get("credit_transfere_rmb") or 0)-applied,0),"credit_target_invoice_id":None}).eq("id",source_id).execute()
        target_id=invoice.get("credit_target_invoice_id");transferred=float(invoice.get("credit_transfere_rmb") or 0)
        if target_id and transferred:
            target=fetch_one("factures_clients",target_id)
            if target:
                try:target_payments=json.loads(target.get("paiements_json") or "[]")
                except (TypeError,ValueError):target_payments=[]
                target_payments=[p for p in target_payments if not isinstance(p,dict) or not (p.get("type")=="credit_transfer" and str(p.get("source_invoice_id"))==str(invoice_id))]
                target_recu=round(float(target.get("recu_rmb") or 0)-transferred,2)
                g.supabase.table("factures_clients").update({"paiements_json":json.dumps(target_payments,ensure_ascii=False),"recu_rmb":target_recu,"reste_rmb":round(float(target.get("total_rmb") or 0)-target_recu,2),"credit_applique_rmb":0,"credit_source_invoice_id":None}).eq("id",target_id).execute()
        g.supabase.table("factures_clients").delete().eq("id", invoice_id).execute()
        flash("Facture client supprimée.", "ok")
    except Exception:
        flash("Suppression impossible.", "error")
    return redirect(url_for("client_invoices"))

@app.route("/factures-clients/new",methods=["GET","POST"])
@app.route("/factures-clients/<int:invoice_id>/edit",methods=["GET","POST"])
def client_invoice_edit(invoice_id=None):
    if not session.get("access_token"): return redirect(url_for("login"))
    try: g.supabase = supabase_client()
    except Exception: session.clear(); return redirect(url_for("login"))
    denied = deny_unless("factures_clients")
    if denied: return denied
    inv=fetch_one("factures_clients", invoice_id) if invoice_id else None
    selected_command_id = request.args.get("commande_id") or (inv or {}).get("commande_id")
    commands=g.supabase.table("commandes").select("*").order("id", desc=True).execute().data
    annotate_command_numbers(commands)
    facture_rows=g.supabase.table("factures").select("id,commande_id,marchandises_rmb,exchange_rate,ocean_freight_usd,ocean_freight_rmb,local_frais_rmb,commission_pct,commission_rmb,autre_charge_rmb,autres_charges_json,frais_coc_rmb,note_charge,montant,total_usd,paiements_json,recu_rmb,reste_rmb").order("id", desc=True).execute().data
    latest_facture={}
    for facture in facture_rows:
        command_id=facture.get("commande_id")
        if command_id is not None and str(command_id) not in latest_facture:
            latest_facture[str(command_id)]=facture
    credit_rows=g.supabase.table("factures_clients").select("id,numero,client,reste_rmb,credit_transfere_rmb").order("id",desc=True).execute().data
    credit_by_client={}
    for credit_row in credit_rows:
        client_key=str(credit_row.get("client") or "").strip().casefold()
        available=max(-float(credit_row.get("reste_rmb") or 0)-float(credit_row.get("credit_transfere_rmb") or 0),0)
        if available>0.005 and client_key not in credit_by_client:
            credit_by_client[client_key]={"amount":round(available,2),"source_invoice_id":credit_row.get("id"),"source_numero":credit_row.get("numero")}
    for command in commands:
        command["saved_facture"]=latest_facture.get(str(command.get("id")))
        command["automatic_invoice_no"]=command.get("invoice_no") or automatic_invoice_number(command)
        command["available_credit"]=credit_by_client.get(str(command.get("client") or "").strip().casefold())
    if request.method=="POST":
        cmd=fetch_one("commandes", request.form.get("commande_id"))
        def amount(name):
            try: return float(request.form.get(name) or 0)
            except ValueError: return 0
        def json_rows(name):
            try:
                rows=json.loads(request.form.get(name) or "[]")
                return rows if isinstance(rows,list) else []
            except (TypeError,ValueError): return []
        if not cmd:
            flash("Choisissez une commande valide.", "error")
            return redirect(request.url)
        payments=[p for p in json_rows("paiements_json") if not isinstance(p,dict) or p.get("type")!="credit_transfer"]
        extra_fees=json_rows("autres_frais_json")
        merchandise=amount("marchandises_rmb"); rate=amount("exchange_rate"); freight_usd=amount("ocean_freight_usd"); freight_rmb=round(freight_usd*rate,2); commission=round(merchandise*amount("commission_pct")/100,2)
        recu=0
        for payment in payments:
            if isinstance(payment,dict):
                try:
                    payment_amount=float(payment.get("amount") or 0); payment_rate=float(payment.get("rate") or 0); currency=payment.get("currency", "RMB")
                    recu += payment_amount if currency == "RMB" else (payment_amount / payment_rate if currency == "DHS" and payment_rate else payment_amount * payment_rate)
                except (TypeError,ValueError): pass
        recu=round(recu,2)
        lines=[{"label":"Total amount des marchandises","amount":merchandise},{"label":"Ocean Freight RMB","amount":freight_rmb},{"label":"Local Frais RMB","amount":amount("local_frais_rmb")},{"label":"Commission RMB","amount":commission},{"label":"Frais COC RMB","amount":amount("frais_coc_rmb")}]
        for fee in extra_fees:
            if isinstance(fee,dict):
                try: lines.append({"label":str(fee.get("label") or "Autre frais"),"amount":float(fee.get("amount") or 0)})
                except (TypeError,ValueError): pass
        extra_fee_total=round(sum(x["amount"] for x in lines[5:]),2)
        total=round(sum(x["amount"] for x in lines),2)
        old_source_id=(inv or {}).get("credit_source_invoice_id")
        old_credit=float((inv or {}).get("credit_applique_rmb") or 0)
        candidates=g.supabase.table("factures_clients").select("id,numero,reste_rmb,credit_transfere_rmb,credit_target_invoice_id").eq("client",cmd["client"]).order("id",desc=True).execute().data
        if invoice_id: candidates=[row for row in candidates if int(row.get("id") or 0)<int(invoice_id)]
        credit_source=None;credit_applied=0
        for candidate in candidates:
            available=max(-float(candidate.get("reste_rmb") or 0)-float(candidate.get("credit_transfere_rmb") or 0),0)
            if str(candidate.get("id"))==str(old_source_id): available+=old_credit
            if available>0.005:
                credit_source=candidate;credit_applied=round(available,2);break
        if credit_source:
            payments.append({"type":"credit_transfer","amount":credit_applied,"currency":"RMB","rate":1,
                             "date":request.form.get("date_facture") or date.today().isoformat(),
                             "place":"Solde antérieur","source_invoice_id":credit_source["id"],
                             "source_numero":credit_source.get("numero")})
            recu=round(recu+credit_applied,2)
        numbered_cmd=next((c for c in commands if str(c.get("id"))==str(cmd.get("id"))),cmd)
        values={"numero":((inv or {}).get("numero") or cmd.get("invoice_no") or automatic_invoice_number(numbered_cmd)),"commande_id":cmd["id"],"client":cmd["client"],"date_facture":(request.form.get("date_facture") or None),"lignes_json":json.dumps(lines,ensure_ascii=False),"marchandises_rmb":merchandise,"exchange_rate":rate,"ocean_freight_usd":freight_usd,"ocean_freight_rmb":freight_rmb,"local_frais_rmb":amount("local_frais_rmb"),"commission_pct":amount("commission_pct"),"commission_rmb":commission,"autre_charge_rmb":extra_fee_total,"frais_coc_rmb":amount("frais_coc_rmb"),"note_charge":request.form.get("note_charge"),"paiements_json":json.dumps(payments,ensure_ascii=False),"autres_frais_json":json.dumps(extra_fees,ensure_ascii=False),"total_rmb":total,"total_usd":round(total/rate,2) if rate else 0,"recu_rmb":recu,"reste_rmb":round(total-recu,2),"credit_applique_rmb":credit_applied,"credit_source_invoice_id":credit_source.get("id") if credit_source else None,"notes":request.form.get("notes"),"updated_by":session["user"]["id"]}
        if invoice_id:
            g.supabase.table("factures_clients").update(values).eq("id", invoice_id).execute();saved_invoice_id=invoice_id
        else:
            values["created_by"]=session["user"]["id"]
            saved=g.supabase.table("factures_clients").insert(values).execute().data;saved_invoice_id=saved[0]["id"]
        new_source_id=credit_source.get("id") if credit_source else None
        if old_source_id and str(old_source_id)!=str(new_source_id):
            old_source=fetch_one("factures_clients",old_source_id)
            if old_source:g.supabase.table("factures_clients").update({"credit_transfere_rmb":max(float(old_source.get("credit_transfere_rmb") or 0)-old_credit,0),"credit_target_invoice_id":None}).eq("id",old_source_id).execute()
        if credit_source:
            transferred=float(credit_source.get("credit_transfere_rmb") or 0)
            if str(old_source_id)==str(new_source_id):transferred=max(transferred-old_credit,0)
            g.supabase.table("factures_clients").update({"credit_transfere_rmb":round(transferred+credit_applied,2),"credit_target_invoice_id":saved_invoice_id}).eq("id",new_source_id).execute()
        linked_facture=latest_facture.get(str(cmd.get("id")))
        if linked_facture:
            g.supabase.table("factures").update({"paiements_json":json.dumps(payments,ensure_ascii=False),"recu_rmb":recu,
                                                  "reste_rmb":round(float(linked_facture.get("montant") or total)-recu,2)}).eq("id",linked_facture["id"]).execute()
        rebuild_client_credit_chain(cmd.get("client"))
        return redirect(url_for("client_invoices"))
    command_data=json.loads(json.dumps(commands,default=str,ensure_ascii=False))
    return render_template("client_invoice_form.html",invoice=inv,commands=commands,command_data=command_data,tables=TABLES,
                           today=date.today().isoformat(),selected_command_id=selected_command_id)

@app.route("/factures-clients/<int:invoice_id>/pdf")
def client_invoice_pdf(invoice_id):
    if not session.get("access_token"): return redirect(url_for("login"))
    try: g.supabase = supabase_client()
    except Exception: session.clear(); return redirect(url_for("login"))
    denied = deny_unless("factures_clients")
    if denied: return denied
    inv=fetch_one("factures_clients", invoice_id)
    if not inv: return redirect(url_for("client_invoices"))
    credit_source=fetch_one("factures_clients",inv.get("credit_source_invoice_id")) or {}
    credit_target=fetch_one("factures_clients",inv.get("credit_target_invoice_id")) or {}
    command=fetch_one("commandes", inv.get("commande_id")) or {}
    commands_all=g.supabase.table("commandes").select("id,client,date_commande").order("date_commande").order("id").execute().data
    command["_client_order_no"]=command_number_map(commands_all).get(str(command.get("id")),inv.get("commande_id"))
    def rows(value):
        try:
            parsed=json.loads(value or "[]")
            return parsed if isinstance(parsed,list) else []
        except (TypeError,ValueError): return []
    def money(value):
        try: return f"{float(value or 0):,.2f}"
        except (TypeError,ValueError): return "0.00"
    buf=BytesIO();doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=16*mm,bottomMargin=16*mm);s=getSampleStyleSheet()
    story=[Paragraph("<b>ISA - FACTURE CLIENT</b>",s["Title"]),Paragraph("YIWU ISA TRADING CO., LIMITED",s["Normal"]),Spacer(1,7*mm),Table([["Facture",inv["numero"]],["Client",inv["client"]],["Commande",f'#{command.get("_client_order_no") or inv["commande_id"]}'],["Date",inv["date_facture"]]],colWidths=[45*mm,110*mm]),Spacer(1,5*mm)]
    client_data=[["INFORMATIONS CLIENT",""] , ["CONSIGNEE",command.get("consignee") or "-"],["ADDRESS",command.get("address") or "-"],["TELEPHONE",command.get("telephone") or "-"],["ICE",command.get("ice") or "-"]]
    client_style=TableStyle([('SPAN',(0,0),(-1,0)),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7f6ec')),('TEXTCOLOR',(0,0),(-1,0),colors.HexColor('#10233e')),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#8bb99a')),('FONTNAME',(0,1),(0,-1),'Helvetica-Bold'),('PADDING',(0,0),(-1,-1),7)])
    story += [Table(client_data,colWidths=[45*mm,115*mm],style=client_style),Spacer(1,5*mm)]
    shipping_data=[["INFORMATIONS D'EXPEDITION",""] , ["Shipper",command.get("shipper") or "-"],["B/L No",command.get("bl_no") or "-"],["Container No",command.get("container_no") or "-"]]
    shipping_style=TableStyle([('SPAN',(0,0),(-1,0)),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dceaff')),('TEXTCOLOR',(0,0),(-1,0),colors.HexColor('#10233e')),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#8ba8cf')),('FONTNAME',(0,1),(0,-1),'Helvetica-Bold'),('PADDING',(0,0),(-1,-1),7)])
    story += [Table(shipping_data,colWidths=[45*mm,115*mm],style=shipping_style),Spacer(1,7*mm)]
    fee_rows=[]
    for line in rows(inv.get("lignes_json")):
        label=str(line.get("label") or "Frais"); amount=line.get("amount") or 0
        if label == "Ocean Freight RMB":
            fee_rows.append(["Ocean Freight",money(inv.get("ocean_freight_usd")),money(amount)])
        else: fee_rows.append([label,"",money(amount)])
    fee_data=[["Description","Montant USD","Montant RMB"]]+fee_rows
    table_style=[('GRID',(0,0),(-1,-1),.5,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#10233e')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('ALIGN',(1,1),(-1,-1),'RIGHT'),('PADDING',(0,0),(-1,-1),8)]
    story += [Paragraph("<b>FRAIS DE LA FACTURE</b>",s["Heading3"]),Table(fee_data,colWidths=[95*mm,30*mm,35*mm],style=TableStyle(table_style)),Spacer(1,7*mm)]
    payments=rows(inv.get("paiements_json"))
    if not payments and float(inv.get("recu_rmb") or 0)>0: payments=[{"amount":inv.get("recu_rmb"),"date":"-","place":"-"}]
    payment_data=[["#","Date","Lieu","Devise","Montant","Taux RMB","Montant RMB"]]
    for i,p in enumerate(payments,1):
        currency=p.get("currency") or "RMB"; rate=float(p.get("rate") or (1 if currency == "RMB" else 0)); amount=float(p.get("amount") or 0); converted=amount if currency == "RMB" else (amount/rate if currency == "DHS" and rate else amount*rate)
        payment_place=(f"Solde de {p.get('source_numero') or credit_source.get('numero') or 'facture precedente'}" if p.get("type")=="credit_transfer" else (p.get("place") or "-"))
        payment_data.append([str(i),p.get("date") or "-",payment_place,currency,money(p.get("amount")),money(rate),money(converted)])
    story += [Paragraph("<b>PAIEMENTS RECUS</b>",s["Heading3"]),Table(payment_data,colWidths=[8*mm,27*mm,18*mm,18*mm,27*mm,27*mm,35*mm],style=TableStyle(table_style)),Spacer(1,8*mm)]
    raw_balance=float(inv.get("reste_rmb") or 0);transferred=float(inv.get("credit_transfere_rmb") or 0);available=max(-raw_balance-transferred,0)
    summary=[["TOTAL RMB",money(inv.get("total_rmb"))],["RECU",money(inv.get("recu_rmb"))],["RESTE A PAYER",money(max(raw_balance,0))],["SOLDE CLIENT DISPONIBLE",money(available)]]
    if float(inv.get("credit_applique_rmb") or 0)>0:summary.append([f"SOLDE ANTERIEUR RECU DE {credit_source.get('numero') or 'FACTURE PRECEDENTE'}",money(inv.get("credit_applique_rmb"))])
    if transferred>0:summary.append([f"SOLDE TRANSFERE VERS {credit_target.get('numero') or 'FACTURE SUIVANTE'}",money(transferred)])
    summary_style=TableStyle([('GRID',(0,0),(-1,-1),.8,colors.HexColor('#10233e')),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#eaf2ff')),('FONTNAME',(0,0),(-1,-1),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),12),('ALIGN',(1,0),(1,-1),'RIGHT'),('PADDING',(0,0),(-1,-1),10)])
    story += [Paragraph("<b>RESUME</b>",s["Heading3"]),Table(summary,colWidths=[105*mm,55*mm],style=summary_style),Spacer(1,7*mm),Paragraph(f'<b>Notes:</b> {escape(str(inv.get("notes") or "-"))}',s["Normal"])]
    doc.build(story);buf.seek(0);return send_file(buf,mimetype="application/pdf",as_attachment=True,download_name=f'{inv["numero"]}.pdf')

@app.route("/frais-maroc-clients")
def morocco_fees():
    if not session.get("access_token"): return redirect(url_for("login"))
    try: g.supabase=supabase_client()
    except Exception: session.clear(); return redirect(url_for("login"))
    denied = deny_unless("frais_maroc_clients")
    if denied: return denied
    rows=g.supabase.table("frais_maroc_clients").select("*").order("id",desc=True).execute().data
    annotate_display_ids(rows)
    commands_all=g.supabase.table("commandes").select("id,client,date_commande").order("date_commande").order("id").execute().data
    numbers=command_number_map(commands_all)
    for row in rows: row["_commande_no"]=numbers.get(str(row.get("commande_id")),row.get("commande_id"))
    q=request.args.get("q","").strip(); needle=q.casefold().lstrip("#")
    if needle: rows=[r for r in rows if needle in str(r.get("numero") or "").casefold() or needle in str(r.get("client") or "").casefold() or needle==str(r.get("commande_id") or "")]
    return render_template("morocco_fees.html",rows=rows,q=q,tables=TABLES)

@app.route("/frais-maroc-clients/new",methods=["GET","POST"])
@app.route("/frais-maroc-clients/<int:fee_id>/edit",methods=["GET","POST"])
def morocco_fee_edit(fee_id=None):
    if not session.get("access_token"): return redirect(url_for("login"))
    try: g.supabase=supabase_client()
    except Exception: session.clear(); return redirect(url_for("login"))
    denied = deny_unless("frais_maroc_clients")
    if denied: return denied
    fee=fetch_one("frais_maroc_clients",fee_id) if fee_id else None
    commands=g.supabase.table("commandes").select("id,client,produit,bl_no,container_no").order("id",desc=True).execute().data
    annotate_command_numbers(commands)
    def json_value(value,fallback):
        try: return json.loads(value or fallback)
        except (TypeError,ValueError): return json.loads(fallback)
    if fee: fee["tva_options"]=json_value(fee.get("tva_options_json"),"{}")
    if request.method=="POST":
        command=fetch_one("commandes",request.form.get("commande_id"))
        if not command:
            flash("Choisissez une commande valide.","error")
            return redirect(request.url)
        def amount(name):
            try: return max(float(request.form.get(name) or 0),0)
            except (TypeError,ValueError): return 0
        extras=json_value(request.form.get("autres_frais_json"),"[]"); vat=json_value(request.form.get("tva_options_json"),"{}")
        extras=extras if isinstance(extras,list) else []; vat=vat if isinstance(vat,dict) else {}
        normalized=[]
        for x in extras:
            if not isinstance(x,dict): continue
            try: value=max(float(x.get("amount") or 0),0)
            except (TypeError,ValueError): value=0
            normalized.append({"label":str(x.get("label") or "Autre frais").strip() or "Autre frais","amount":value,"tva":bool(x.get("tva"))})
        fixed=("transitaire_dhs","douane_dhs","coc_dhs","telex_dhs","portnet_dhs","frais_service_isa_dhs")
        fixed_values={name:amount(name) for name in fixed}; other_total=round(sum(x["amount"] for x in normalized),2)
        subtotal=round(sum(fixed_values.values())+other_total,2)
        tax=round(sum(value*.2 for name,value in fixed_values.items() if vat.get(name))+sum(x["amount"]*.2 for x in normalized if x["tva"]),2)
        values={"numero":request.form.get("numero"," ").strip(),"commande_id":command["id"],"client":command.get("client") or "","date_frais":request.form.get("date_frais") or None,**fixed_values,"autres_frais_json":json.dumps(normalized,ensure_ascii=False),"autre_total_dhs":other_total,"tva_options_json":json.dumps(vat,ensure_ascii=False),"sous_total_ht_dhs":subtotal,"tva_total_dhs":tax,"total_dhs":round(subtotal+tax,2),"notes":request.form.get("notes","").strip(),"updated_by":session["user"]["id"]}
        try:
            if fee_id: g.supabase.table("frais_maroc_clients").update(values).eq("id",fee_id).execute()
            else: values["created_by"]=session["user"]["id"];g.supabase.table("frais_maroc_clients").insert(values).execute()
        except Exception:
            flash("Enregistrement impossible.","error");return redirect(request.url)
        flash("Frais Maroc enregistrés.","ok");return redirect(url_for("morocco_fees"))
    return render_template("morocco_fee_form.html",fee=fee,commands=commands,tables=TABLES,today=date.today().isoformat())

@app.post("/frais-maroc-clients/<int:fee_id>/delete")
def morocco_fee_delete(fee_id):
    if not session.get("access_token"): return redirect(url_for("login"))
    try: g.supabase=supabase_client()
    except Exception: session.clear(); return redirect(url_for("login"))
    denied = deny_unless("frais_maroc_clients")
    if denied: return denied
    if session.get("role")!="admin": flash("Suppression réservée à l’administrateur.","error");return redirect(url_for("morocco_fees"))
    try: g.supabase.table("frais_maroc_clients").delete().eq("id",fee_id).execute();flash("Dossier supprimé.","ok")
    except Exception: flash("Suppression impossible.","error")
    return redirect(url_for("morocco_fees"))

def build_morocco_fee_pdf(fee,command):
    def m(value):
        try:return f"{float(value or 0):,.2f}"
        except (TypeError,ValueError):return "0.00"
    def parsed(value,fallback):
        try:return json.loads(value or fallback)
        except (TypeError,ValueError):return json.loads(fallback)
    vat=parsed(fee.get("tva_options_json"),"{}");extras=parsed(fee.get("autres_frais_json"),"[]")
    labels=[("Transitaire","transitaire_dhs"),("Douane Maroc","douane_dhs"),("COC","coc_dhs"),("Change Telex","telex_dhs"),("PortNet","portnet_dhs"),("Frais de service societe ISA","frais_service_isa_dhs")]
    lines=[]
    for label,key in labels:
        value=float(fee.get(key) or 0)
        if value: lines.append([label,m(value),"20%" if vat.get(key) else "-",m(value*.2 if vat.get(key) else 0),m(value*1.2 if vat.get(key) else value)])
    for x in extras if isinstance(extras,list) else []:
        value=float(x.get("amount") or 0);taxable=bool(x.get("tva"));lines.append([str(x.get("label") or "Autre frais"),m(value),"20%" if taxable else "-",m(value*.2 if taxable else 0),m(value*1.2 if taxable else value)])
    buf=BytesIO();doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=16*mm,leftMargin=16*mm,topMargin=15*mm,bottomMargin=15*mm);s=getSampleStyleSheet()
    info=[["N dossier",fee.get("numero") or "-"],["Client",fee.get("client") or "-"],["Commande",f"#{command.get('_client_order_no') or fee.get('commande_id') or '-'}"],["N B/L",command.get("bl_no") or "-"],["N Container",command.get("container_no") or "-"],["Date",fee.get("date_frais") or "-"]]
    story=[Paragraph("<b>ISA - FRAIS MAROC CLIENT</b>",s["Title"]),Paragraph("Dépenses avancées au Maroc par ISA",s["Normal"]),Spacer(1,6*mm),Table(info,colWidths=[42*mm,120*mm],style=TableStyle([('GRID',(0,0),(-1,-1),.5,colors.HexColor('#aebed1')),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#eaf2ff')),('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),('PADDING',(0,0),(-1,-1),7)])),Spacer(1,6*mm)]
    data=[["Description","Montant HT","TVA","TVA DHS","Total TTC"]]+lines
    story.append(Table(data,colWidths=[66*mm,27*mm,18*mm,25*mm,30*mm],repeatRows=1,style=TableStyle([('GRID',(0,0),(-1,-1),.5,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#10233e')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('ALIGN',(1,1),(-1,-1),'RIGHT'),('PADDING',(0,0),(-1,-1),7)])))
    summary=[["SOUS-TOTAL HT",m(fee.get("sous_total_ht_dhs"))],["TVA 20%",m(fee.get("tva_total_dhs"))],["TOTAL TTC",m(fee.get("total_dhs"))]]
    story += [Spacer(1,7*mm),Table(summary,colWidths=[105*mm,55*mm],hAlign='RIGHT',style=TableStyle([('GRID',(0,0),(-1,-1),.7,colors.HexColor('#10233e')),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#e7f6ec')),('FONTNAME',(0,0),(-1,-1),'Helvetica-Bold'),('ALIGN',(1,0),(1,-1),'RIGHT'),('PADDING',(0,0),(-1,-1),9)])),Spacer(1,7*mm),Paragraph(f"<b>Notes:</b> {escape(str(fee.get('notes') or '-'))}",s["Normal"])]
    doc.build(story);buf.seek(0);return buf

@app.route("/frais-maroc-clients/<int:fee_id>/pdf")
def morocco_fee_pdf(fee_id):
    if not session.get("access_token"): return redirect(url_for("login"))
    try:g.supabase=supabase_client()
    except Exception:session.clear();return redirect(url_for("login"))
    denied = deny_unless("frais_maroc_clients")
    if denied: return denied
    fee=fetch_one("frais_maroc_clients",fee_id)
    if not fee:return redirect(url_for("morocco_fees"))
    command=fetch_one("commandes",fee.get("commande_id")) or {}
    commands_all=g.supabase.table("commandes").select("id,client,date_commande").order("date_commande").order("id").execute().data
    command["_client_order_no"]=command_number_map(commands_all).get(str(command.get("id")),fee.get("commande_id"))
    return send_file(build_morocco_fee_pdf(fee,command),mimetype="application/pdf",as_attachment=True,download_name=f"{fee.get('numero') or 'frais-maroc'}.pdf")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5039")), debug=False)
