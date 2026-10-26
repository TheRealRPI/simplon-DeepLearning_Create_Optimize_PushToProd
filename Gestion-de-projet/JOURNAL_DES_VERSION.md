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
| 22/10/2026 17h04 | `3a8147c` | Local | Mise à jour du notebook `model_creation_optimisation.ipynb` avec les étapes 3 et 4, modification de `PLAN.md` (102 lignes), mise à jour de `pyproject.toml` et `.gitignore` | ✅ Push réussi sur GitHub |
| 23/10/2026 12h13 | `36cec04` | Local | Finalisation du notebook `model_creation_optimisation.ipynb` : refactor complet avec variables globales (EPOCH, BATCH, etc.), ajout d'un modèle quantifié, création des fichiers `model/metrics.json`, `model/model.keras`, `model/model.tflite`, `model/reference.csv`, `model/vectoriseur.joblib`, mise à jour de `PLAN.md` | ✅ Push réussi sur GitHub |
| 23/10/2026 12h20 | `6be54f5` | Local | Mise à jour de `PLAN.md` (26 lignes modifiées) et du journal des versions | ✅ Push réussi sur GitHub |
| 23/10/2026 16h33 | `a925a76` | Local | Ajout de l'API : création des fichiers `src/deeplearning_create_optimize_pushtoprod/api.py` et `src/deeplearning_create_optimize_pushtoprod/model_loader.py`, mise à jour de `.gitignore`, `pyproject.toml` et `uv.lock` | ✅ Push réussi sur GitHub |
| 26/10/2026 10h29 | `0f8fc73` | Local | Modification de l'API avec détection de la langue : refonte de `model_loader.py`, évolution de `api.py`, mise à jour de `PLAN.md`, `pyproject.toml` et `uv.lock` | ✅ Push réussi sur GitHub |
| 26/10/2026 12h33 | `41520a3` | Local | Tests automatiques et barrière qualité : ajout de `quality_gate.py`, `config.yaml`, `model/faux_metrics.json`, création de la suite de tests (`tests/conftest.py`, `tests/test_api.py`, `tests/test_quality_gate.py`), mise à jour de `PLAN.md` | ✅ Push réussi sur GitHub |
| 26/10/2026 14h47 | `1d7a02b` | Local | API conteneurisée via Docker : ajout du `Dockerfile` et `.dockerignore`, mise à jour de `requirements.txt` et `PLAN.md` | ✅ Push réussi sur GitHub |
| 26/10/2026 15h07 | `fdf5cee` | Local | Phase 4 (4.1 + 4.2) : pipeline CI/CD GitHub Actions (`.github/workflows/pipeline.yml`) avec jobs `test` (Python 3.13, barrière qualité, pytest) et `image` (build Docker + smoke test `/health` et `/predict`), runners `ubuntu-26.04` épinglés, correctif `.gitignore` (exception `!.github/`) | ✅ Push réussi sur GitHub |
| 26/10/2026 15h10 | `fdf5cee` | CI (GitHub Actions) | Run #1 : job `test` VERT (0:32 — barrière qualité acceptée + pytest OK) puis job `image` VERT (0:48 — build + smoke test conteneur). URL : `actions/runs/40336844450` | ✅ 2 jobs verts |

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

*Dernière mise à jour : 26/10/2026 15h00*
