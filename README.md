# FASTHOME

Plateforme immobilière Django pour la RDC : marketplace, matching, visites sécurisées, contrats, paiements et suivi locatif autour d'un **compte utilisateur unique**.

## Stack
- Python 3.12+
- Django 4.2.7
- SQLite en développement (PostgreSQL recommandé en production)
- HTML/CSS responsive
- Pillow et qrcode prévus pour les médias et documents

## Démarrage

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

## Fonctionnalités

### Marketplace
- Accueil FASTHOME responsive
- Recherche par ville, commune, quartier et type
- Recherche tolérante aux variantes de quartier
- Résultats triés par score de matching
- Fiche bien avec caractéristiques et confidentialité
- Favoris par session

### Compte unique
Un même compte peut simultanément rechercher, publier, visiter, louer et gérer des biens. Le système ne demande pas de choisir « propriétaire » ou « locataire » à l'inscription.

### Publications
- Brouillon
- En vérification
- Validée
- Publiée séparément de la validation
- Refusée avec motif obligatoire
- Louée / archivée

### Visites
- Demande de visite
- Notifications au demandeur et au propriétaire
- Date et heure préférées
- Double approbation propriétaire + FASTHOME
- Programmation et rapport de visite côté opérations

### Contrats / paiements
- Références uniques de biens et contrats
- Vérification d'un contrat par référence
- Suivi des paiements et échéances
- Paiement hors plateforme : FASTHOME enregistre l'opération

### Back-office
- `/gestion/` : tableau de bord opérationnel pour les comptes staff
- Vérification des publications
- Validation distincte de la publication publique
- Gestion des visites
- `/admin/` : administration Django complète avec recherches et filtres

### Sécurité UX
- Prix exact et adresse exacte absents du marketplace public
- Coordonnées du propriétaire non exposées
- Contrôle `is_staff` pour le back-office
- Protection CSRF, sessions HTTP-only et permissions Django
- Pages 403, 404, 500 et maintenance

## CI
GitHub Actions exécute `pip install -r requirements.txt`, `python manage.py check` et `python manage.py migrate --noinput` sur `main`.

## Prochaine étape production
Pour une version production complète, brancher PostgreSQL, stockage média privé, vraie galerie photo, PDF/QR de contrats, documents signés, audit détaillé, calendrier persistant et notifications planifiées.
