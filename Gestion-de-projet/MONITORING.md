# 📊 Monitoring du modèle — Documentation

> **Ce que le dispositif mesure, comment, et comment décider.** Monitoring du **modèle**
> (dérive, régression) — pas de l'infrastructure (latence, uptime, 5xx → Prometheus/Grafana,
> hors périmètre).
>
> Réalisé dans le cadre du brief « Deep Learning — Create, Optimize, Push to Prod » · 28/10/2026

---

## 1. Objectif et périmètre

Le dispositif répond à **quatre questions** :

| Question | Réponse apportée par |
|---|---|
| Les données d'entrée ont-elles changé ? | **Dérive** des descripteurs (Evidently, fenêtre glissante) |
| Le modèle déployé est-il conforme à ses métriques annoncées ? | **Golden set** (400 lignes rejouées via HTTP) |
| Comment suivre l'évolution des métriques ? | **Rapports** HTML/JSON horodatés (+ MLflow, phase bonus) |
| Faut-il réentraîner ? | **Table de décision** (§5) qui combine les deux mesures |

**Ce qui est mesuré** : la dérive des entrées (`longueur`, `nb_mots`, `oov_rate`), la dérive
des prédictions (`proba`), le F1 réellement servi (golden set), les rejets 422 par motif.

**Ce qui n'est PAS mesuré** : la précision sur le trafic réel (impossible sans labels — §7),
l'infra (CPU, mémoire, latence réseau), la disponibilité.

---

## 2. Architecture — pourquoi deux images

```
                 ┌────────────────────────────────────────────┐
  Client ─HTTP─► │  film-api (Dockerfile, image de 665 Mo)     │
                 │  preprocessing → TF-IDF → LiteRT           │
                 │  /predict ──► 1 ligne JSONL (non bloquant) │
                 └───────────────┬────────────────────────────┘
                                 │ volume partagé /data
                                 ▼
                 ┌────────────────────────────────────────────┐
                 │  predictions.jsonl + rapports + mlflow.db  │
                 └───────────────┬────────────────────────────┘
                                 │ lecture batch
                                 ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  film-monitoring (Dockerfile.monitoring, image de 1,87 Go)    │
  │  JOB BATCH — jamais un service                                │
  │  collect.py → drift.py → golden_set.py → __main__.py          │
  └──────────────────────────────────────────────────────────────┘
```

**Deux images séparées, pour quatre raisons** :

1. **Taille** : evidently + mlflow pèsent 1,2 Go — tripler l'image de service (665 Mo → 1,87 Go)
   pour 2 endpoints serait absurde ;
2. **Surface d'attaque** : mlflow apporte une dizaine de CVE à une image qui serait exposée
   publiquement — le job, lui, n'est jamais exposé ;
3. **Séparation des préoccupations** : le hot path (constat : 1 ligne JSONL, stdlib) ne doit
   pas porter l'analyse (calculs lourds, ponctuels) ;
4. **Cycle de vie** : l'API tourne en continu, le monitoring s'exécute à la demande
   (`docker compose run`, job CI) et s'arrête en produisant ses rapports.

> [!IMPORTANT]
> **Contrainte A1, respectée par construction** : l'image de service ne gagne
> AUCUNE dépendance. Le log JSONL est écrit en stdlib pure (`predictions_log.py`,
> `descriptors.py` = stdlib + langdetect déjà présent). `requirements.txt` est inchangé.

---

## 3. La ligne de log JSONL — le « constat »

Chaque requête `/predict` produit **une ligne** dans `predictions.jsonl` (volume `/data`),
écrite en tâche de fond, **jamais bloquante** (une panne de log ne casse jamais la
prédiction — testé) :

```json
{
  "ts": "2026-10-28T14:03:22.481Z",
  "request_id": "b3f1c2a4e7d8…",
  "source": "production",
  "route": "/predict",
  "status": 200,
  "motif": null,
  "latency_ms": 12.4,
  "model_version": "1.1.0",
  "image_version": "local",
  "texte": "A family moves into an old mansion…",
  "descripteurs": { "longueur": 312, "nb_mots": 54, "langue": "en", "oov_rate": 0.112 },
  "prediction": { "proba": 0.9823, "classe": 1, "seuil": 0.5 }
}
```

| Champ | Rôle | Pourquoi |
|---|---|---|
| `ts` | fenêtre glissante | limite l'analyse aux 30 derniers jours |
| `request_id` | traçabilité | une ligne = une requête identifiable |
| `source` | filtrage | `production` vs `golden_set` — **sans ce filtre, le rejeu du golden set fausserait la dérive** |
| `status` + `motif` | rejets | les 422 n'atteignent jamais le modèle : sans eux, le trafic paraît stable alors qu'il s'effondre (`langue:it`, `trop_court`, `vide_apres_nettoyage`, `corps_invalide`…) |
| `latency_ms` | diagnostic | mesuré **côté handler** (début → fin de calcul), jamais en tâche de fond |
| `model_version` + `image_version` | attribution | une chute de F1 doit être rattachable à un release précis → actionnable |
| `texte` | revue humaine | texte **nettoyé** (celui vu par le modèle) — résumés de films, aucune donnée personnelle |
| `descripteurs` | dérive | calculés via `vectorizer.build_analyzer()` — jamais une tokenisation maison |
| `prediction` | dérive de proba | la classe est un **int** recalculé depuis `probabilite > 0.5` |

> [!WARNING]
> **Concurrence** : les BackgroundTasks de Starlette loggent en parallèle (threadpool).
> Un **verrou de processus** sérialise les écritures (lignes > 8 Ko : sans verrou, elles
> s'entrelacent — 114 lignes corrompues mesurées avant correction, + test de régression).
> Il n'y a PAS de verrou **fichier** : plusieurs répliques de l'API ne sont pas supportées (§7).

---

## 4. Les indicateurs (et leur calibrage)

### `oov_rate` — le signal principal de dérive d'entrées

**Part de tokens absents du vocabulaire TF-IDF (9 005 termes)**, calculée avec l'analyzer
du vectoriseur servi. Si le taux monte, les utilisateurs emploient un vocabulaire que le
modèle n'a jamais vu pendant l'entraînement.

> [!NOTE]
> **Calibrage (mesuré en P0 sur la référence de 2 400 lignes)** : μ = 0,536, σ = 0,069 —
> les tokens incluent les bigrammes, majoritairement hors vocabulaire : un `oov_rate`
> « normal » tourne autour de 0,5, pas de 0. Le seuil d'alerte `oov_rate_max = 0.70`
> (μ+2σ) remplace la valeur 0,25 initialement prévue, qui aurait alerté en permanence.

### Dérive de prédiction (`proba`)

La distribution des probabilités servies est comparée à celle de la référence. Bimodale
en trafic normal (le modèle est confiant) : μ = 0,499 ± 0,456 sur la référence. Elle
détecte ce que le golden set ne voit pas — un changement de comportement sur des
**entrées nouvelles**.

### F1 golden set — la conformité de l'artefact servi

Les 400 lignes de `model/reference.csv` sont **rejouées via HTTP** sur l'API déployée
(en-tête `X-Monitoring-Source: golden_set`), avec 2 tentatives par requête. Une ligne qui
échoue (422/5xx/réseau) compte comme une **erreur de prédiction**, jamais comme un skip.

| Valeur | Rôle |
|---|---|
| **F1 = 0,8713** (`f1_reference_golden_set`) | baseline **mesurée** en P0 sur l'API locale — ce n'est PAS `f1_score_test` (0,8571, jeu de test seul) : le golden set mêle `y_test` et `y_prod` |
| `f1_minimum = 0.83` | seuil d'**alerte** (miroir de la barrière qualité) |
| écart vs baseline | **diagnostic** : distingue une régression d'artefact d'une dérive des données |

### Rejets 422 par motif

Comptés séparément, jamais mélangés à la dérive : un effondrement du trafic valide caché
derrière des rejets `langue:fr` massifs serait invisible autrement. *(Exemple réel observé
en démo : un résumé du corpus détecté `langue:it` — un rejet, logué, compté.)*

### Seuils de la dérive (section `monitoring:` de `config.yaml`)

| Seuil | Valeur | Calibration |
|---|---|---|
| `drift_share_max` | 0,30 | part max de colonnes en dérive (partage Evidently) |
| `value_drift_seuil` | 0,30 | distance de Wasserstein normée par colonne — le défaut Evidently (0,1) sature sur le **bruit d'échantillonnage** d'une fenêtre de ~150 lignes (0,08–0,15 mesuré en trafic sain) ; 0,30 sépare le bruit d'une vraie dérive (5,5 mesurée sur un jeu décalé) |
| `oov_rate_max` | 0,70 | μ+2σ sur la référence P0 (cf. ci-dessus) |
| `fenetre_min_lignes` | 100 | garde-fou : moins de lignes → exit 2, pas d'alerte — 3 requêtes ne font pas une dérive |

---

## 5. La table de décision — faut-il réentraîner ?

C'est **cette table qui répond au brief**. Le job l'affiche à chaque exécution et adapte
le code de sortie :

| Dérive | Golden set | Diagnostic | Action |
|---|---|---|---|
| non | conforme | sain | rien |
| non | régression | **artefact déployé cassé** | **rollback** — PAS un réentraînement |
| oui | conforme | les données changent, le modèle tient | rafraîchir le jeu d'entraînement |
| oui | régression | dégradation réelle | **réentraînement** |

**Codes de sortie du job** (`python -m …monitoring`) :

| Code | Signification | Effet CI |
|---|---|---|
| 0 | sain | vert |
| 1 | dérive détectée OU F1 < seuil | **rouge / alerte** |
| 2 | données production insuffisantes | neutre (warning) |
| 3 | API injoignable | rouge |

> [!IMPORTANT]
> Le code 1 sur dérive seule n'est pas une « panne » : c'est le signal **consulter la
> table**. Une régression d'artefact se corrige par rollback en minutes ; un réentraînement
> sur ce cas figerait le problème dans un nouveau modèle.

---

## 6. Cadence et exécution

### Quand ?

1. **Après chaque release** (job CI `monitoring` — automatique, cf. §6.2) ;
2. **À la demande** (investigation, démonstration) ;
3. **Ponctuellement en production** — une évolution cible est un déclencheur hebdomadaire
   (Container App Job, §8), pas encore implémentée.

Ce n'est **ni** un service, **ni** un cron : la dérive est un job batch.

### Comment ?

**Local / démo (compose)** — le plus complet :

```bash
mkdir -p data/monitoring                        # sinon Docker le crée root → log silencieusement absent
docker compose up -d api                        # image API + volume partagé
docker compose run --rm monitoring             # job → rapports dans data/monitoring/reports/
docker compose --profile ui up -d mlflow        # (bonus P4) UI MLflow sur :5000
```

Résultat mesuré en démo : golden set **F1 = 0,8713 (écart 0,0000 vs baseline)** sur l'API
conteneurisée, dérive non détectée sur 119 requêtes réelles, **exit 0**. Sans trafic
production : exit 2 (neutre, par conception).

**CI (job `monitoring`, après `image`)** — rebuild des 2 images (runner neuf par job,
cache GHA), démarrage de l'API conteneurisée + attente `/health`, exécution du job
`--no-mlflow`, tolérance de l'exit 2 (pas de trafic production en CI), archivage des
rapports en artefact. Exit 1/3 → pipeline rouge.

**Directement en local (sans Docker)** :

```bash
uv sync --group monitoring
uv run uvicorn deeplearning_create_optimize_pushtoprod.api:app --port 8000 &
API_URL=http://localhost:8000 PREDICTIONS_LOG=/tmp/predictions.jsonl \
  uv run python -m deeplearning_create_optimize_pushtoprod.monitoring --no-mlflow
```

### Procédure de réentraînement (rôle des scripts P0)

Les deux scripts `scripts/` sont des outils **côté entraînement**, exécutés une fois par
réentraînement — pas par le job :

```
1. Notebook                                    → nouveau model.tflite + vectoriseur + metrics.json
2. uv run python scripts/build_reference_drift.py  → régénère reference_drift.csv + meta.json
                                                   (~40 s : nettoyer_texte + descripteurs + proba
                                                    sur les 2 400 lignes — PAS d'API nécessaire)
3. API up + uv run python scripts/check_golden_set.py  → re-mesure la baseline F1 (~10 s)
4. Figer la valeur mesurée dans config.yaml (f1_reference_golden_set)
5. Committer les artefacts (reference_drift.csv, meta.json, reports/golden_set_baseline.json)
```

> [!WARNING]
> L'étape 2 **avant le commit** est non négociable : le sidecar `reference_drift.meta.json`
> doit porter le `model_version` du nouveau modèle. Le job de monitoring **compare le
> sidecar à `metrics.json` au démarrage** et prévient (warning) si la référence est
> périmée — sinon la dérive comparerait des distributions de deux modèles différents.

---

## 7. Limites assumées

| # | Limite | Assomption |
|---|---|---|
| 1 | **Pas de mesure de précision en production** | Sans labels sur le trafic réel, seul le golden set mesure le F1. Une revue humaine exigerait ~300 labels/fenêtre pour être statistiquement valide → documentée comme évolution (§8), pas implémentée |
| 2 | **Golden set figé** | C'est un test de **non-régression**, pas un thermomètre : il garantit que l'artefact servi prédit comme le jour de la baseline, pas que le modèle est bon sur des données nouvelles |
| 3 | **IC95 du F1 golden set** | ±2,5 points à n = 400 → un écart de ±0,02 avec la baseline est du **bruit**, pas une régression. Le seuil d'alerte (0,83) est loin de l'IC ; la baseline sert au diagnostic, pas à l'alerte |
| 4 | **Une seule réplique d'API** | Pas de verrou fichier : deux répliques écriraient des lignes entrelacées. (Le verrou de **processus** contre les BackgroundTasks concurrentes est, lui, nécessaire et testé.) Un fichier par réplique si le besoin apparaît |
| 5 | **Filesystem éphémère en Container Apps** | Le JSONL sur volume local ne survit pas à un redéploiement Azure → en cloud réel, il faut un stockage persistant (§8). Tout est démontrable en local via compose |
| 6 | **Un changement de `nettoyer_texte` produit une dérive « normale »** | Les descripteurs décrivent ce que voit le vectoriseur : si le nettoyage change, la distribution change sans que le modèle ait bougé. Le champ `image_version` logué rattache la dérive au release qui l'a causée |
| 7 | **Evidently 0.7 ≠ tutoriels 0.4** | Tous les tutoriels en ligne sont en 0.4 (`DataDriftTable`, `DatasetDriftMetric`, presets) — retirés. Pièges rencontrés : `save_html()` exige un **str** (un Path n'écrit rien, sans erreur) ; le schéma de résultats est `metric_name`/`value` ; `DriftedColumnsCount` teste avec SES seuils internes → la décision utilise les tests par colonne calibrés |
| 8 | **Versions épinglées** | `requirements-monitoring.txt` fige la combinaison validée (evidently 0.7.23, pandas 3.0.6, mlflow 3.17.2) : pip a résolu un pandas 3.1 dont `infer_dtype_from_object` — importé par le module de compatibilité interne d'evidently — a été retiré → ImportError en conteneur. Changer une version = revalider les 6 scénarios |

---

## 8. Évolutions cibles

| Évolution | Quoi | Pourquoi |
|---|---|---|
| **Boucle de labellisation** | Échantillonner le trafic, labelliser (revue humaine ou heuristique), entraîner sur les corrections | Activer le F1 en production (lève la limite 1) — sous ~300 labels/fenêtre, elle automatiserait du bruit |
| **Stockage persistant** | Azure Blob (`wasbs://`) pour le JSONL, Postgres/MySQL pour le backend MLflow | Le filesystem d'une Container App est éphémère ; sqlite local ne survit pas (limite 5) |
| **Container App Job** | Déclencheur hebdomadaire du job de monitoring côté Azure | Équivalent cloud du job CI, sur le trafic réel |
| **Registry MLflow** | `registry.py` (pyfunc TFLite) — phase bonus P4 | Cycle MLOps complet défendable à l'oral |

---

## En trois phrases (soutenance)

1. Le dispositif **sépare ce qui constate** — une ligne JSONL par requête, en stdlib pure
   dans l'image de service, jamais bloquante — **de ce qui analyse** : un job batch dans
   une seconde image, qui n'est jamais exposée.
2. La dérive est mesurée par `oov_rate` — la part de vocabulaire hors du TF-IDF, calibrée
   sur une référence de 2 400 lignes mesurée — et le golden set de 400 lignes **rejoué via
   HTTP** vérifie que l'artefact réellement servi n'a pas régressé (F1 = 0,8713, écart 0
   avec la baseline).
3. La décision de réentraîner **distingue régression d'artefact** (→ rollback en minutes)
   de **dérive des données** (→ rafraîchir l'entraînement) ; la précision en production
   n'étant pas mesurable sans labels, cette limite est assumée et documentée.

---

*Job : `python -m deeplearning_create_optimize_pushtoprod.monitoring [--no-mlflow] [--api-url URL]` ·
Seuils : section `monitoring:` de `config.yaml` · Références internes : plan §6.5 (table), §4.1 (baseline).*
