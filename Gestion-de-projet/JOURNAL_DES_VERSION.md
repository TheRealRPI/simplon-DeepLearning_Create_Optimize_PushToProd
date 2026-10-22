# JOURNAL DES VERSIONS

> Historique des versions déployées et des commits marquants du projet.
>
> Projet : Classification de résumés de films (horreur vs comédie)
> Dépôt : https://github.com/TheRealRPI/simplon-DeepLearning_Create_Optimize_PushToProd

---

## Légende

| Colonne | Description |
|---------|-------------|
| **Date** | Date et heure du déploiement/commit (heure locale) |
| **Identifiant** | Hash court du commit Git (7 caractères) ou tag de version |
| **Environnement** | Local, CI (GitHub Actions), ou Production (Azure) |
| **Changement** | Description des modifications apportées |
| **Résultat** | ✅ Succès / ❌ Échec / ⏳ En cours |

---

## Historique

| Date | Identifiant | Environnement | Changement | Résultat |
|------|-------------|---------------|------------|----------|
| 22/10/2026 10h00 | `92cea0e` | Local (dépôt initialisé) | Initialisation du repo : structure de dossiers, `pyproject.toml`, `requirements.txt`, `uv.lock`, `.gitignore`, `PLAN.md`, données brutes (`Data/textes_films_horreur_comedie.csv`, 2400 lignes), squelette du package Python | ✅ Push réussi sur GitHub |
| 22/10/2026 11h58 | `7c7b395` | Local | Ajout du notebook `model_creation_optimisation.ipynb` contenant les étapes 1 et 2 de création et optimisation du modèle, mise à jour de `PLAN.md`, `pyproject.toml` et `uv.lock` | ✅ Push réussi sur GitHub |

---

## Versions déployées en production (Azure)

> Cette section sera remplie lors des déploiements sur Azure Container Apps (Phase 5 du plan).

| Date | Identifiant commit | Tag image Docker | Environnement | Changement | Résultat |
|------|--------------------|------------------|---------------|------------|----------|
| — | — | — | — | *Aucun déploiement en production pour l'instant* | — |

---

## Notes

- **22/10/2026** : Premier commit `92cea0e` — mise en place de la structure du projet et du document de planification (PLAN.md). Le fichier de données `textes_films_horreur_comedie.csv` (2400 résumés de films) est versionné dans `Data/`.
- Les déploiements en production (Azure) seront consignés dans la section dédiée ci-dessus, avec l'identifiant du commit et le tag de l'image Docker associée.
- Chaque déploiement manuel sur Azure devra être tracé ici avec la date, le commit déployé, et le résultat du test `/health`.

---

*Dernière mise à jour : 22/10/2026 12h00*
