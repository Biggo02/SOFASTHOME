# FASTHOME

Plateforme immobilière Django pour la RDC : marketplace, matching, visites, contrats, paiements et suivi locatif autour d'un compte utilisateur unique.

## Stack
- Python 3.12+
- Django 4.2.7
- SQLite en développement (PostgreSQL recommandé en production)
- HTML/CSS responsive
- Pillow et qrcode prévus pour médias et documents

## Lancer le projet

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Puis ouvrir `http://127.0.0.1:8000/`.

## Principes déjà implémentés
- Compte unique polyvalent
- Recherche et filtres de biens
- Matching expliqué
- Confidentialité du loyer et de l'adresse publique
- Publications avec brouillon / vérification / validation / publication / location
- Demandes de visite
- Contrats avec références uniques et page de vérification
- Paiements et échéances
- Notifications
- Dashboard personnel responsive
- Back-office Django Admin

## Architecture d'évolution
Les modules suivants peuvent être séparés en apps lorsque le produit entre en production : users, properties, matching, visits, contracts, payments, documents, notifications, dashboard, audit, geolocation et reports.
