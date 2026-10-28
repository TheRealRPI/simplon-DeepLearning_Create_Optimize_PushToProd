"""
Rapports Evidently — dérive des entrées/prédictions + classification golden set.

⚠️ API Evidently 0.7 UNIQUEMENT (R1) : `Report(metrics=[...])`, `DataDefinition`,
`Dataset.from_pandas()`, `report.run(current_data=..., reference_data=...)`,
`save_html()/.json()` sur l'objet RETOURNÉ par run(). Tous les tutoriels en
ligne sont en 0.4 (DataDriftTable, DatasetDriftMetric, ClassificationPreset,
`from evidently.report import Report`) — ces presets ont été RETIRÉS.

Deux rapports :
1. DÉRIVE (ce module) : DriftedColumnsCount + ValueDrift par colonne, sur
   production vs référence — jamais de dérive sur texte brut (NLTK ⇒
   dépendance réseau ; oov_rate est un signal plus propre, §6.2) ;
2. CLASSIFICATION (visualisation du golden set) : Accuracy/F1/Precision/Recall
   sur les lignes rejouées. Les métriques de DÉCISION (F1 avec la convention
   « erreur = prédiction fausse ») restent calculées dans golden_set.py :
   Evidently ne sait pas représenter un échec de requête comme erreur.

Règles d'alerte (config.yaml `monitoring:`) :
- share de colonnes dérivées > drift_share_max  → dérive ;
- oov_rate moyen production > oov_rate_max      → dérive (signal principal).

Env :
    MONITORING_REPORTS_DIR  dossier des rapports (défaut ./reports,
                            /data/reports en compose/CI)

Auteur : TheRealRPI
Date   : 28/10/2026
"""

# =============================================================================
# IMPORTS
# =============================================================================

import json
from os import getenv
from pathlib import Path

import pandas as pd
from evidently import BinaryClassification, DataDefinition, Dataset, Report
from evidently.metrics import (
    Accuracy,
    DriftedColumnsCount,
    F1Score,
    Precision,
    Recall,
    ValueDrift,
)

# =============================================================================
# CONSTANTES
# =============================================================================

# local : ./reports du dépôt · compose/CI : MONITORING_REPORTS_DIR=/data/reports
REPORTS_DIR = Path(getenv("MONITORING_REPORTS_DIR", "reports"))

# Colonnes communes production/référence — l'ordre fixe l'affichage du rapport
COLONNES_DERIVE = ["longueur", "nb_mots", "oov_rate", "proba"]


# =============================================================================
# RAPPORT DE DÉRIVE
# =============================================================================


def analyser_derive(
    production: pd.DataFrame,
    reference: pd.DataFrame,
    drift_share_max: float,
    oov_rate_max: float,
    value_drift_seuil: float,
    horodatage: str,
) -> dict:
    """Rapport Evidently de dérive → {derive, resume, rapports}.

    Args :
        production        : DataFrame (longueur, nb_mots, oov_rate, proba) — fenêtre ;
        reference         : DataFrame de reference_drift.csv (P0) ;
        drift_share_max    : seuil d'alerte sur la part de colonnes dérivées ;
        oov_rate_max      : seuil d'alerte absolu sur le signal principal ;
        value_drift_seuil : seuil de distance (Wasserstein normée) par colonne —
                            calibré, le défaut Evidently (0.1) sature sur le bruit
                            d'échantillonnage d'une fenêtre de 150 lignes ;
        horodatage        : suffixe des fichiers de rapport (YYYY-MM-DD_HHMM).
    """
    definition = DataDefinition(numerical_columns=COLONNES_DERIVE)
    rapport = Report(
        [
            DriftedColumnsCount(drift_share=drift_share_max),
            ValueDrift(column="oov_rate", threshold=value_drift_seuil),  # signal principal
            ValueDrift(column="longueur", threshold=value_drift_seuil),
            ValueDrift(column="nb_mots", threshold=value_drift_seuil),
            ValueDrift(column="proba", threshold=value_drift_seuil),  # dérive de prédiction
        ]
    )

    # kwargs 0.7 : current_data / reference_data (jamais current=/reference=)
    # Les DataFrames passent par Dataset.from_pandas avec la DataDefinition.
    snapshot = rapport.run(
        current_data=Dataset.from_pandas(production[COLONNES_DERIVE], data_definition=definition),
        reference_data=Dataset.from_pandas(reference[COLONNES_DERIVE], data_definition=definition),
    )

    # Écriture des rapports — ⚠️ save_html() exige un str : avec un Path il
    # n'écrit RIEN, sans lever (piège mesuré sur Evidently 0.7).
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    chemin_html = REPORTS_DIR / f"drift_{horodatage}.html"
    chemin_json = REPORTS_DIR / f"drift_{horodatage}.json"
    snapshot.save_html(str(chemin_html))

    donnees = _en_dict(snapshot)
    chemin_json.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")

    resume = _resumer_derive(donnees)

    # DÉCISION (règles §6.2) — calculée sur les tests par colonne CALIBRÉS
    # (threshold=value_drift_seuil), pas sur le compteur interne de
    # DriftedColumnsCount : celui-ci teste avec le défaut Evidently (0.1),
    # trop sensible pour une fenêtre de ~150 lignes (share 0.5 en trafic
    # sain, mesuré en P2). Sa valeur reste rapportée à titre informatif.
    nb_colonnes = len(COLONNES_DERIVE)
    share_calibre = len(resume["colonnes_derivees"]) / nb_colonnes
    resume["share_calibre"] = round(share_calibre, 4)

    oov_moyen = float(production["oov_rate"].mean())
    derive = share_calibre > float(drift_share_max) or oov_moyen > float(oov_rate_max)

    return {
        "derive": derive,
        "resume": resume,
        "rapport_html": str(chemin_html),
        "rapport_json": str(chemin_json),
    }


def _en_dict(snapshot) -> dict:
    """Résultat du run() en dict, quel que le nom exact de la méthode 0.7."""
    if hasattr(snapshot, "dict"):
        return snapshot.dict()
    return json.loads(snapshot.json())


def _resumer_derive(donnees: dict) -> dict:
    """Extraction des résultats — schéma réel Evidently 0.7 (vérifié au runtime).

    Chaque métrique : {"metric_name": "ValueDrift(column=oov_rate,...)",
                       "config": {"column": ..., "threshold": ...},
                       "value": <distance Wasserstein normée> ou {"count", "share"}}.
    """
    resume: dict = {
        "colonnes_derivees": [],
        "nb_colonnes_derivees": None,
        "share_colonnes_derivees": None,
        "distances": {},
    }
    for metrique in donnees.get("metrics", []):
        nom = str(metrique.get("metric_name", ""))
        config = metrique.get("config") or {}
        valeur = metrique.get("value")

        if nom.startswith("DriftedColumnsCount"):
            if isinstance(valeur, dict):
                resume["nb_colonnes_derivees"] = valeur.get("count")
                resume["share_colonnes_derivees"] = valeur.get("share")

        elif nom.startswith("ValueDrift") and isinstance(valeur, (int, float)):
            colonne = str(config.get("column", "?"))
            seuil = float(config.get("threshold", 0.1))
            resume["distances"][colonne] = round(float(valeur), 4)
            if float(valeur) > seuil:
                resume["colonnes_derivees"].append(colonne)

    return resume


# =============================================================================
# RAPPORT DE CLASSIFICATION (golden set — visualisation)
# =============================================================================


def rapport_classification(df_golden: pd.DataFrame, horodatage: str) -> Path:
    """Rapport Evidently des métriques de classification sur le golden set rejoué.

    df_golden doit contenir `cible` (vérité) et `classe` (prédite, int 0/1).
    Les échecs de requête — déjà comptés comme prédictions fausses par
    golden_set.py — sont exclus ici : ce rapport est une VISUALISATION.
    """
    definition = DataDefinition(
        classification=[BinaryClassification(target="cible", prediction_labels="classe", pos_label=1)]
    )
    rapport = Report([Accuracy(), F1Score(), Precision(), Recall()])
    snapshot = rapport.run(
        current_data=Dataset.from_pandas(df_golden, data_definition=definition)
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    chemin = REPORTS_DIR / f"classification_{horodatage}.html"
    snapshot.save_html(str(chemin))  # str obligatoire (cf. note save_html ci-dessus)
    return chemin
