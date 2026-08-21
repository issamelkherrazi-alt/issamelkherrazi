# ISA ERP V26.5

Application online de gestion commerciale et logistique pour YIWU ISA TRADING, avec authentification et base partagée Supabase.

Modules: tableau de bord, clients, commandes, factures, paiements, livraisons et COC.

Les paiements des factures acceptent RMB, USD et DHS, avec un taux de conversion propre à chaque paiement vers RMB.

La référence client saisie dans la commande génère automatiquement le numéro de facture au format `RD-2026N1`, puis `RD-2026N2` pour les commandes suivantes du même client. Ce numéro reste synchronisé dans Factures, Factures Clients et les PDF.

Le module Demandes Clients conserve les demandes à ne pas oublier, leur commande liée, la priorité, la date limite et la confirmation. Les demandes à confirmer ou en retard remontent automatiquement dans les urgences du tableau de bord.

La modification du total des marchandises dans une commande recalcule automatiquement les factures fournisseur et client liées (commission, totaux et reste à payer).

Un client ajouté dans le module Clients est automatiquement proposé dans les formulaires Commandes, Factures et Paiements.

## Configuration

Copier `.env.example` vers `.env` et définir une clé secrète Flask. Le projet Supabase et sa clé publique sont déjà indiqués dans l'exemple.

Créer les comptes employés dans Supabase Auth. Le compte `issamelkherrazi@gmail.com` reçoit automatiquement le rôle Admin; les autres comptes reçoivent le rôle Employé.

## Démarrage local

- Terminal: `python3 -m pip install -r requirements.txt && python3 app.py`
- Adresse V26.5 CLIENT REQUESTS: http://127.0.0.1:5039

En production: `gunicorn app:app`. Définir `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` et `FLASK_SECRET_KEY` dans l'hébergeur.

Les employés peuvent consulter, ajouter et modifier. La suppression est réservée à l'Admin et cette règle est imposée dans la base, pas seulement dans l'interface.


V45 PATCH EDIT: fixes Factures Clients /edit 500 by sanitizing command JSON; preserves existing invoice/order numbering on edit. No database schema changes.

V45 PATCH EDIT V2: empty date_facture is stored as NULL instead of empty string, fixing PostgreSQL date error on Facture Client edit.
