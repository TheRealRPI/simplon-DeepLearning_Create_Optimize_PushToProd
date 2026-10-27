# PLAN.md - Projet Deep Learning : Create, Optimize, Push to Prod

> **Classification de résumés de films (horreur vs comédie)** - Du notebook au déploiement Azure
>
> Auteur : TheRealRPI | Date de planification : 22/10/2026 | Deadline : **28/10/2026**

---

## 1. Contexte et objectifs

### 1.1 Contexte

Ce projet s'inscrit dans le brief de mise en production d'un modèle de Deep Learning. L'objectif est de partir d'un jeu de données de résumés de films, de créer un modèle de classification (horreur vs comédie), de l'optimiser, puis de le déployer en production via une API FastAPI conteneurisée sur Azure.

### 1.2 Objectifs du projet

| # | Objectif | Critère de réussite |
|---|----------|---------------------|
| O1 | Créer un modèle de classification performant | F1 > seuil défini sur le jeu de test |
| O2 | Optimiser les hyperparamètres | Comparaison KerasTuner vs Optuna (20 essais chacun) |
| O3 | Exposer le modèle via une API | Routes `/health` et `/predict` fonctionnelles |
| O4 | Automatiser les tests et la qualité | Tests pytest + barrière qualité (config.yaml) |
| O5 | Conteneuriser l'application | Image Docker construite et testée localement |
| O6 | Automatiser le CI/CD | Workflow GitHub Actions avec 3 jobs (test, image, publier) |
| O7 | Déployer en production | Application Azure accessible publiquement |
| O8 | Gérer le cycle de vie | Déploiement manuel, retour arrière, fin de vie des ressources |
| O9 | Documenter la gestion de projet | PLAN.md, PROCEDURE_MISE_EN_PRODUCTION.md, JOURNAL_DES_VERSION.md, FIN_DE_VIE.md |

### 1.3 Périmètre

**Inclus :**
- Notebook Jupyter en 8 parties (audit → sauvegarde)
- API FastAPI avec validation Pydantic
- Tests automatiques (pytest)
- Barrière qualité (config.yaml + script de vérification)
- Dockerfile + .dockerignore
- Workflow GitHub Actions (CI/CD)
- Déploiement Azure (Container Apps + ACR)
- Documentation de gestion de projet (4 fichiers)

**Exclus :**
- Déploiement automatique (CD) - déploiement manuel imposé par les droits Azure
- Interface utilisateur web (API REST uniquement)
- Monitoring avancé (hors scope du brief)

---

## 2. Ressources allouées

### 2.1 Ressources humaines

| Rôle | Personne | Disponibilité | Responsabilités |
|------|----------|---------------|-----------------|
| Développeur / Data Scientist | TheRealRPI (seul) | **5 jours × 6h30 = 32h30** (22, 23, 26, 27, 28/10, 9h-17h pauses comprises) | Développement complet : notebook, API, tests, Docker, CI/CD, déploiement, documentation |
| Formateur / Évaluateur | - | Ponctuel | Validation des jalons (étape 12 : montrer l'adresse publique) |

### 2.2 Ressources matérielles

| Ressource | Description | Utilisation |
|-----------|-------------|-------------|
| Poste de développement | PC Windows avec GPU CUDA | Entraînement des modèles, développement local, tests Docker |
| GPU (CUDA) | Carte graphique compatible TensorFlow | Accélération de l'entraînement (TensorFlow[and-cuda]) |

### 2.3 Ressources techniques

| Ressource | Description | Utilisation |
|-----------|-------------|-------------|
| Python 3.13+ | Environnement de développement | Langage principal |
| TensorFlow[and-cuda] >= 2.21 | Framework Deep Learning | Construction et entraînement du réseau de neurones |
| KerasTuner >= 1.4.7 | Recherche d'hyperparamètres | RandomSearch (20 essais) |
| Optuna >= 4.0.0 | Recherche d'hyperparamètres | Comparaison avec KerasTuner |
| scikit-learn >= 1.7.0 | ML classique + métriques | Modèles de référence (LogisticRegression, MultinomialNB), TF-IDF, F1 |
| FastAPI >= 0.118.0 | Framework API | Exposition du modèle via HTTP |
| Docker | Conteneurisation | Image de production |
| GitHub | Dépôt de code + CI/CD | Versioning, Actions, secrets |
| Azure (compte formation) | Cloud provider | Registre ACR + Container Apps |
| Jupyter / ipykernel | Notebook | Développement du modèle |

### 2.4 Ressources financières

| Ressource | Coût estimé | Notes |
|-----------|-------------|-------|
| Azure Container Registry (Basic) | ~5€/mois | Facturé tant que le registre existe, à supprimer en fin de vie |
| Azure Container Apps (1 vCPU, 2 Go RAM) | ~30-50€/mois | Consommation à l'usage, à supprimer en fin de vie |
| GitHub (gratuit) | 0€ | Dépôt public ou privé gratuit |
| **Total estimé (5 jours)** | **~5-10€** | Coût réel à relever à l'étape 15 (ménage) |

---

## 3. Planning macro - Vue d'ensemble

> **Horaires journaliers :** 9h00–17h00 (8h) avec pauses comprises = **6h30 de travail effectif/jour**
> - Pause matin : 10h15–10h30 (15 min)
> - Pause repas : 12h30–13h30 (1h)
> - Pause après-midi : 15h15–15h30 (15 min)
>
> **5 jours travaillés** : 22, 23, 26, 27, 28 octobre 2026 (mercredi, jeudi, lundi, mardi, mercredi)
> **Total : 5 × 6h30 = 32h30 de travail effectif**

| Jour | Date | Phase(s) | Charge | Cumul |
|------|------|----------|--------|-------|
| **J1** | 22/10 (mer.) | Phase 0 - Mise en place + Phase 1 (début) | 1,00 j | 1,00 j |
| **J2** | 23/10 (jeu.) | Phase 1 - Notebook (fin) | 1,00 j | 2,00 j |
| **J3** | 26/10 (lun.) | Phase 2 - API + Tests + Qualité + Phase 3 - Docker + Phase 4 (début) | 1,00 j | 3,00 j |
| **J4** | 27/10 (mar.) | Phase 4 (fin) + Phase 5 - Azure + Phase 6 - Gestion versions | 1,00 j | 4,00 j |
| **J5** | 28/10 (mer.) | Phase 7 - Ménage + Phase 8 - Documentation + Livraison | 1,00 j | **5,00 j** |

| Phase | Description | Durée estimée | Jour(s) |
|-------|-------------|---------------|---------|
| **Phase 0** | Mise en place de l'environnement et du dépôt | 0,20 j | J1 (22/10) matin |
| **Phase 1** | Notebook - Création et optimisation du modèle (8 parties) | 1,80 j | J1 après-midi → J2 (23/10) |
| **Phase 2** | API FastAPI + Tests + Barrière qualité | 0,55 j | J3 (26/10) matin |
| **Phase 3** | Conteneurisation Docker | 0,25 j | J3 (26/10) début après-midi |
| **Phase 4** | CI/CD GitHub Actions | 0,45 j | J3 fin après-midi → J4 (27/10) matin |
| **Phase 5** | Déploiement Azure + Tests en production | 0,50 j | J4 (27/10) après-midi |
| **Phase 6** | Gestion des versions (déploiement, rollback) | 0,20 j | J4 (27/10) fin après-midi |
| **Phase 7** | Fin de vie et ménage | 0,25 j | J5 (28/10) matin |
| **Phase 8** | Documentation gestion de projet + preuves + livraison | 0,80 j | J5 (28/10) après-midi |
| **TOTAL** | | **5,00 j** | **22/10 → 28/10** |

> **Note :** 1 jour = 6h30 de travail effectif (9h-17h avec pauses). Pas de marge calendaire, les estimations intègrent une marge interne de ~10% sur les tâches à risque.

---

## 4. Planning détaillé - Tableau des tâches

> **Légende des ressources :** H = Humaines, M = Matérielles, T = Techniques, F = Financières
> **Unité :** 1 jour = 6h30 de travail effectif (9h00–17h00, pauses comprises)
> **Pauses fixes :** 10h15–10h30 | 12h30–13h30 (repas) | 15h15–15h30

| # | Tâche | Dépend de | Charge estimée (jours) | Charge réelle (jours) | Ressources | Date prévue |
|---|-------|-----------|------------------------|-----------------------|------------|-------------|
| **PHASE 0 - Mise en place (0,20 j)** | | | **0,20** | **0,12** | | **J1 - 22/10 matin** |
| 0.1 | Créer le dépôt GitHub + structure de dossiers | - | 0,05 | 0,05 | H, T (GitHub) | 22/10 09h00–09h20 |
| 0.2 | Configurer l'environnement Python (uv, venv, dépendances) | 0.1 | 0,10 | 0,00 | H, M, T (Python, uv) | 22/10 09h20–10h15 |
| 0.3 | Vérifier l'accès GPU/CUDA + placer le CSV dans `data/` | 0.2 | 0,05 | 0,07 | H, M (GPU), T (dataset) | 22/10 10h30–10h55 |
| **PHASE 1 - Notebook, 8 parties (1,80 j)** | | | **1,80** | **1,27** | | **J1 après-midi → J2 - 22-23/10** |
| 1.1 | Partie 1 : Audit et nettoyage des données | 0.3 | 0,15 | 0,12 | H, M, T (pandas) | 22/10 10h55–12h10 ✅ |
| 1.2 | Partie 2 : Découpage train/val/test/prod (60/20/20) | 1.1 | 0,10 | 0,12 | H, T (sklearn) | 22/10 12h10–12h30 + 13h30–13h50 ✅ |
| 1.3 | Partie 3 : Représentation TF-IDF | 1.2 | 0,15 | 0,12 | H, T (TfidfVectorizer) | 22/10 13h50–14h50 ✅ |
| 1.4 | Partie 4 : Modèles de référence (LogReg, NB, NN simple) + F1 sur 5 graines | 1.3 | 0,25 | 0,12 | H, M, T (sklearn, Keras) | 22/10 14h50–15h15 + 15h30–16h40 ✅ |
| 1.5 | Partie 5 : Recherche KerasTuner (RandomSearch, 20 essais) | 1.4 | 0,25 | 0,40 | H, M (GPU), T (KerasTuner) | 22/10 16h40–17h00 + 23/10 09h00–10h15 ✅ |
| 1.6 | Partie 6 : Recherche Optuna (20 essais, mêmes réglages) + comparaison | 1.5 | 0,25 | 0,12 | H, M (GPU), T (Optuna) | 23/10 10h30–12h10 ✅ |
| 1.7 | Partie 7 : Verdict sur le test (réentraînement, 5 graines, F1 final) | 1.6 | 0,20 | 0,12 | H, M (GPU), T | 23/10 12h10–12h30 + 13h30–14h30 ✅ |
| 1.8 | Partie 8 : Sauvegarde (model.keras, vectoriseur.joblib, metrics.json, reference.csv) | 1.7 | 0,10 | 0,12 | H, T (joblib, json) | 23/10 14h30–15h10 ✅ |
| 1.9 | Vérification : notebook exécutable de haut en bas + commit GitHub | 1.8 | 0,15 | 0,15 | H, T (Git) | 23/10 15h30–16h30 ✅ |
| **PHASE 2 - API + Tests + Qualité (0,55 j)** | | | **0,55** | **1,00** | | **J3 - 26/10** |
| 2.1 | API FastAPI : chargement modèle, routes /health et /predict | 1.9 | 0,20 | 0,38 | H, T (FastAPI, Pydantic) | 26/10 09h00–10h15 + 10h30–10h35 ✅ |
| 2.2 | Validation des entrées + tests manuels locaux (3 cas) | 2.1 | 0,10 | 0,31 | H, M, T (Pydantic) | 26/10 10h35–11h15 ✅ |
| 2.3 | Tests automatiques pytest + barrière qualité (config.yaml + script) | 2.2 | 0,15 | 0,23 | H, T (pytest, httpx, pyyaml) | 26/10 11h15–12h15 ✅ |
| 2.4 | Test de la barrière : modèle accepté + faux modèle refusé | 2.3 | 0,10 | 0,08 | H, T | 26/10 13h30–14h10 ✅ |
| **PHASE 3 - Conteneurisation (0,25 j)** | | | **0,25** | **0,16** | | **J3 - 26/10 après-midi** |
| 3.1 | Dockerfile (image slim, tensorflow-cpu) + .dockerignore | 2.4 | 0,10 | 0,08 | H, T (Docker) | 26/10 14h10–14h50 ✅ |
| 3.2 | Construction de l'image + test du conteneur local (3 cas) | 3.1 | 0,15 | 0,08 | H, M, T (Docker) | 26/10 14h50–15h15 + 15h30–16h00 ✅ |
| **PHASE 4 - CI/CD GitHub Actions (0,45 j)** | | | **0,45** | **0,30** | | **J3 fin après-midi → J4 matin** |
| 4.1 | Workflow GitHub Actions : job `test` (install, barrière qualité, pytest) | 3.2 | 0,15 | 0,10 | H, T (GitHub Actions) | 26/10 16h00–17h00 ✅ |
| 4.2 | Workflow : job `image` (build Docker + vérification démarrage API) | 4.1 | 0,10 | 0,05 | H, T (Docker, Actions) | 27/10 09h00–09h40 ✅ |
| 4.3 | Test du workflow : push → 2 jobs verts + test négatif (seuil impossible) | 4.2 | 0,10 | 0,10 | H, T (GitHub) | 27/10 09h40–10h20 ✅ (fait le 26/10 15h26–16h00) |
| 4.4 | Ajout job `publier` (préparation secrets ACR) | 4.3 | 0,10 | 0,05 | H, T (GitHub Secrets) | 27/10 10h30–11h10 ✅ (fait le 27/10 09h42) |
| **PHASE 5 - Déploiement Azure (0,50 j)** | | | **0,50** | | | **J4 - 27/10 après-midi** |
| 5.1 | Création du registre ACR (Basic) + activation utilisateur admin | 4.4 | 0,10 | 0,05 | H, T, F (Azure) | 27/10 11h10–11h50 ✅ (fait le 27/10 09h16) |
| 5.2 | Ajout des 3 secrets GitHub + job `publier` (login ACR + push image) | 5.1 | 0,10 | 0,10 | H, T (GitHub, Docker) | 27/10 11h50–12h30 ✅ (inclut debug environment, 27/10 09h42–09h47) |
| 5.3 | Test : 3 jobs verts + image dans le registre avec tag commit | 5.2 | 0,10 | 0,05 | H, T (Azure, GitHub) | 27/10 13h30–14h10 ✅ (validé au run #6, 27/10 09h47) |
| 5.4 | Création Azure Container App (1 vCPU, 2 Go, ingress externe) | 5.3 | 0,10 | | H, T, F (Azure) | 27/10 14h10–14h50 |
| 5.5 | Test public : /health et /predict (3 cas) + **JALON formateur** | 5.4 | 0,10 | | H, T (Azure), H (formateur) | 27/10 14h50–15h30 |
| **PHASE 6 - Gestion des versions (0,20 j)** | | | **0,20** | | | **J4 - 27/10 fin après-midi** |
| 6.1 | Ajout route /hello + push + attente 3 jobs verts | 5.5 | 0,05 | 0,05 | H, T (GitHub, Azure) | 27/10 15h30–15h50 ✅ (fait le 27/10 11h14) |
| 6.2 | Déploiement manuel nouvelle image + vérification /hello visible | 6.1 | 0,05 | | H, T, F (Azure) | 27/10 15h50–16h10 |
| 6.3 | Retour arrière : redéploiement ancien commit + vérification | 6.2 | 0,05 | | H, T, F (Azure) | 27/10 16h10–16h30 |
| 6.4 | Rédaction du JOURNAL_DES_VERSION.md | 6.3 | 0,05 | | H | 27/10 16h30–16h50 |
| **PHASE 7 - Fin de vie et ménage (0,25 j)** | | | **0,25** | | | **J5 - 28/10 matin** |
| 7.1 | Relevé du coût estimé Azure + suppression Container App | 6.4 | 0,10 | | H, T, F (Azure) | 28/10 09h00–09h40 |
| 7.2 | Suppression environnement + registre ACR + preuves (captures) | 7.1 | 0,10 | | H, T, F (Azure) | 28/10 09h40–10h20 |
| 7.3 | Rédaction de FIN_DE_VIE.md (composants, procédure, coûts) | 7.2 | 0,05 | | H | 28/10 10h30–10h50 |
| **PHASE 8 - Documentation et finalisation (0,80 j)** | | | **0,80** | | | **J5 - 28/10 après-midi** |
| 8.1 | Rédaction de PROCEDURE_MISE_EN_PRODUCTION.md (1 page) | 6.4 | 0,15 | | H | 28/10 13h30–14h30 |
| 8.2 | Finalisation du PLAN.md (remplir charges réelles, écarts) | 7.3 | 0,15 | | H | 28/10 14h30–15h15 |
| 8.3 | Rédaction du README.md (explication de lancement) | 3.2 | 0,15 | | H | 28/10 15h30–16h30 |
| 8.4 | Fiche d'une page : plan vs réel, écarts, réflexions | 8.2 | 0,15 | | H | 28/10 16h30–17h00 |
| 8.5 | Collecte et organisation de toutes les preuves | 7.2 | 0,10 | | H | 28/10 11h00–11h40 |
| 8.6 | Vérification finale : tous les livrables présents et cohérents | 8.5 | 0,10 | | H | 28/10 11h40–12h20 |

---

## 5. Jalons et points de contrôle

| Jalon | Date/heure prévue | Critère de passage | Validation |
|-------|-------------------|--------------------|------------|
| **J0** - Environnement prêt | 22/10 10h55 | Dépôt GitHub créé, environnement fonctionnel, GPU vérifié, CSV placé | ✅ **Atteint 22/10 10h00** |
| **J1** - Notebook complet | 23/10 16h30 | Notebook exécutable de haut en bas, dossier `model/` complet, commit GitHub | ✅ **Atteint 23/10 12h30** |
| **J2** - API + Qualité OK | 26/10 14h10 | /health et /predict répondent, tests pytest verts, barrière qualité validée | ✅ **Atteint 26/10 14h10** |
| **J3** - Image Docker OK | 26/10 16h00 | Image construite, conteneur local répond comme l'API locale | ✅ **Atteint 26/10 16h00** |
| **J4** - CI/CD vert | 27/10 11h10 | 3 jobs verts, test négatif validé (rouge puis vert) | GitHub Actions |
| **J5** - Production en ligne | 27/10 15h30 | Adresse publique accessible, /health et /predict OK | **Formateur** |
| **J6** - Gestion des versions | 27/10 16h50 | /hello ajouté puis retiré, rollback fonctionnel, journal rédigé | Auto-vérification |
| **J7** - Ménage effectué | 28/10 10h50 | Ressources Azure supprimées, preuves capturées, coût relevé | Auto-vérification |
| **J8** - Livraison finale | 28/10 17h00 | Tous les livrables présents, fiche plan vs réel rédigée | **Deadline** |

---

## 6. Gestion des risques

| # | Risque | Probabilité | Impact | Mitigation |
|---|--------|-------------|--------|------------|
| R1 | Entraînement trop long (KerasTuner/Optuna) | Moyenne | Retard 0,25-0,5 j | Lancer en arrière-plan, réduire essais si besoin, GPU vérifié en J0 |
| R2 | Fuite de données (doublons train/test) | Moyenne | Score faussé, rework | Audit rigoureux partie 1, `drop_duplicates` avant split |
| R3 | KerasTuner s'arrête (errno 22) sous Windows | Moyenne | Blocage Phase 1 | Désactiver écriture fichiers de suivi (voir boîte à outils) |
| R4 | Image Docker trop lourde / conteneur qui redémarre | Moyenne | Blocage Phase 3/5 | `tensorflow-cpu` + image slim, 2 Go RAM minimum sur Azure |
| R5 | Workflow GitHub Actions mal configuré | Moyenne | Retard Phase 4 | Vérifier `.github/workflows/` (avec un **s**), activer Actions |
| R6 | Droits Azure insuffisants (Contributeur) | Faible | Blocage déploiement | Déploiement manuel (imposé), utiliser utilisateur admin du registre |
| R7 | Nom de registre ACR non unique | Faible | Blocage Phase 5 | Nom unique au monde (minuscules, sans tiret) |
| R8 | Mémoire insuffisante sur Azure (redémarrages) | Moyenne | Blocage Phase 5 | Allouer 2 Go minimum, vérifier logs `az containerapp logs` |
| R9 | Oubli de supprimer les ressources Azure | Moyenne | Coût inutile | Phase 7 dédiée, checklist, preuve par capture |
| R10 | Planning trop serré (5 jours, 6h30/jour, pas de marge calendaire) | **Élevée** | Retard livraison | Prioriser les livrables obligatoires, paralléliser où possible, demander aide si blocage > 20 min |

---

## 7. Arborescence cible du projet

```
DeepLearning_Create_Optimize_PushToProd/
├── .github/
│   └── workflows/
│       └── pipeline.yml          # CI/CD (test → image → publier)
├── .gitignore
├── .dockerignore
├── Gestion-de-projet/
│   ├── PLAN.md                   # Ce document
│   ├── JOURNAL_DES_VERSION.md    # Journal des déploiements
│   ├── PROCEDURE_MISE_EN_PRODUCTION.md  # Procédure de déploiement
│   └── FIN_DE_VIE.md             # Plan de fin de vie
├── cours/                        # PDFs du brief (référence)
├── data/
│   └── films.csv                 # Jeu de données (résumés de films)
├── model/
│   ├── model.keras               # Réseau entraîné
│   ├── vectoriseur.joblib        # TF-IDF
│   ├── metrics.json              # F1, version, tailles, versions libs
│   └── reference.csv             # Échantillon de référence
├── notebooks/
│   └── 01_model_creation_optimisation.ipynb  # Notebook en 8 parties
├── src/
│   └── deeplearning_create_optimize_pushtoprod/
│       ├── __init__.py
│       ├── api.py                # API FastAPI (/health, /predict)
│       ├── model_loader.py       # Chargement modèle + vectoriseur
│       └── quality_gate.py       # Script barrière qualité
├── tests/
│   └── test_api.py               # Tests pytest
├── config.yaml                   # Seuils de qualité (F1 min, taille test min)
├── Dockerfile
├── pytest.ini
├── pyproject.toml
├── requirements.txt
├── uv.lock
└── README.md
```

---

## 8. Synthèse des charges

| Phase | Charge estimée (jours) | Charge réelle (jours) | Écart |
|-------|------------------------|-----------------------|-------|
| Phase 0 - Mise en place | 0,20 | **0,12** | **-0,08** (-29 min) |
| Phase 1 - Notebook (8 parties) | 1,80 | **1,27** | **-0,53** |
| Phase 2 - API + Tests + Qualité | 0,55 | **1,00** | **+0,45** |
| Phase 3 - Conteneurisation | 0,25 | **0,16** | **-0,09** |
| Phase 4 - CI/CD GitHub Actions | 0,45 | **0,30** | **-0,15** |
| Phase 5 - Déploiement Azure | 0,50 | | |
| Phase 6 - Gestion des versions | 0,20 | | |
| Phase 7 - Fin de vie et ménage | 0,25 | | |
| Phase 8 - Documentation et finalisation | 0,80 | | |
| **TOTAL** | **5,00** | **2,85** | |

> **Note :** 5,0 jours estimés pour 5 jours travaillés (22, 23, 26, 27, 28/10) à **6h30/jour** (9h-17h avec pauses) = **32h30 effectives**. Pauses fixes : 10h15-10h30, 12h30-13h30 (repas), 15h15-15h30. Pas de marge calendaire, les estimations intègrent une marge interne de ~10% sur les tâches à risque. En cas de dépassement, prioriser les livrables obligatoires du brief.

---

## 9. Références

- Brief C12 : Planifier le projet (`cours/c12-fiche-planifier-le-projet.pdf`)
- Brief suite : Déploiement pipeline production (`cours/suite-deploiement-pipeline-production.pdf`)
- Livrables attendus : PLAN.md, PROCEDURE_MISE_EN_PRODUCTION.md, JOURNAL_DES_VERSION.md, FIN_DE_VIE.md, fiche plan vs réel

---

*Document rédigé le 22/10/2026 - à compléter avec les charges réelles au fur et à mesure du projet.*
