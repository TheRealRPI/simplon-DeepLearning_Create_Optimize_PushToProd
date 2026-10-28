"""
Lecture des données du job monitoring (plan §6.1).

Trois sources :
1. le JSONL des prédictions (volume partagé, écrit par predictions_log.py) ;
2. la distribution de référence model/reference_drift.csv (générée en P0) ;
3. la section `monitoring:` de config.yaml (seuils et fenêtres).

Filtres (le filtre `source` est CRUCIAL : sans lui, le rejeu du golden set
fausserait la dérive ; le filtre `status == 200` sépare la dérive des rejets).

Garde-fou (§6.1) : moins de `fenetre_min_lignes` lignes production dans la
fenêtre → l'orchestrateur sort en 2 (warning), JAMAIS en alerte — 3 requêtes
ne font pas une dérive.

Env :
    PREDICTIONS_LOG  chemin du JSONL (défaut /data/predictions.jsonl)

Auteur : TheRealRPI
Date   : 28/10/2026
"""

# =============================================================================
# IMPORTS
# =============================================================================

import json
from datetime import UTC, datetime, timedelta
from os import getenv
from pathlib import Path

import pandas as pd
import yaml

# =============================================================================
# CHEMINS — racine du projet (identique en local et dans l'image /app)
# =============================================================================

# collect.py vit dans <root>/src/<pkg>/monitoring/ → 4 niveaux
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
REFERENCE_DRIFT_CSV = PROJECT_ROOT / "model" / "reference_drift.csv"
REFERENCE_DRIFT_META = PROJECT_ROOT / "model" / "reference_drift.meta.json"
METRICS_JSON = PROJECT_ROOT / "model" / "metrics.json"

# /data = volume partagé en compose/CI ; en local, passer PREDICTIONS_LOG en env
LOG_PATH = Path(getenv("PREDICTIONS_LOG", "/data/predictions.jsonl"))

# =============================================================================
# PARAMÈTRES — section monitoring: de config.yaml
# =============================================================================

# Valeurs de repli si la section manquait (config.yaml reste LA source de vérité)
DEFAUTS = {
    "fenetre_jours": 30,
    "fenetre_min_lignes": 100,
    "drift_share_max": 0.30,
    "oov_rate_max": 0.70,
    "f1_minimum": 0.83,
    "f1_reference_golden_set": 0.8713,
}


def charger_parametres(chemin: Path | None = None) -> dict:
    """Lit la section `monitoring:` de config.yaml (repli sur DEFAUTS si absente)."""
    chemin = chemin or CONFIG_PATH
    try:
        with open(chemin, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"⚠️ {chemin} introuvable — valeurs par défaut utilisées")
        return dict(DEFAUTS)
    section = config.get("monitoring") or {}
    parametres = {**DEFAUTS, **section}
    if not section:
        print(f"⚠️ Section `monitoring:` absente de {chemin} — valeurs par défaut")
    return parametres


# =============================================================================
# JSONL — lecture tolérante aux lignes corrompues
# =============================================================================


def charger_jsonl(chemin: Path | None = None) -> tuple[list[dict], int]:
    """Lit le JSONL en ignorant les lignes corrompues (comptées + warning).

    La non-fatalité côté écriture (A2) implique des lignes partielles
    possibles (crash au milieu d'un write) : le job doit les tolérer.
    """
    chemin = chemin or LOG_PATH
    if not chemin.exists():
        return [], 0

    lignes: list[dict] = []
    corrompues = 0
    with open(chemin, encoding="utf-8") as f:
        for brute in f:
            brute = brute.strip()
            if not brute:
                continue
            try:
                lignes.append(json.loads(brute))
            except json.JSONDecodeError:
                corrompues += 1

    if corrompues:
        print(f"⚠️ {corrompues} ligne(s) corrompue(s) ignorée(s) dans {chemin.name}")
    return lignes, corrompues


# =============================================================================
# TRAFIC PRODUCTION — fenêtre glissante → DataFrame de dérive
# =============================================================================


def charger_production(lignes: list[dict], fenetre_jours: int) -> pd.DataFrame:
    """Filtre source=production + status=200 sur la fenêtre glissante.

    Retourne un DataFrame (longueur, nb_mots, oov_rate, proba) — exactement
    les colonnes du rapport de dérive. Les lignes incomplètes (descripteurs
    ou prédiction absents) sont exclues de la dérive mais RESTENT dans les
    compteurs de rejets.
    """
    maintenant = datetime.now(UTC)
    borne = maintenant - timedelta(days=fenetre_jours)

    production: list[dict] = []
    for ligne in lignes:
        if ligne.get("source") != "production" or ligne.get("status") != 200:
            continue
        try:
            ts = datetime.fromisoformat(ligne["ts"])
        except (KeyError, ValueError, TypeError):
            continue  # ts illisible → hors fenêtre par sécurité
        if ts.tzinfo is None:  # défensive : ts toujours UTC côté écriture
            ts = ts.replace(tzinfo=UTC)
        if ts < borne:
            continue

        descripteurs = ligne.get("descripteurs") or {}
        prediction = ligne.get("prediction") or {}
        production.append(
            {
                "longueur": descripteurs.get("longueur"),
                "nb_mots": descripteurs.get("nb_mots"),
                "oov_rate": descripteurs.get("oov_rate"),
                "proba": prediction.get("proba"),
            }
        )

    df = pd.DataFrame(production)
    if not df.empty:
        avant = len(df)
        df = df.dropna().reset_index(drop=True)
        if len(df) < avant:
            print(f"⚠️ {avant - len(df)} ligne(s) production incomplète(s) exclue(s) de la dérive")
    return df


# =============================================================================
# REJETS — 422 par motif + 500, indicateur séparé (jamais mélangé à la dérive)
# =============================================================================


def charger_rejets(lignes: list[dict]) -> dict[str, int]:
    """Agrège les 422 par motif et les 500.

    Les 422 n'atteignent jamais le modèle : sans cet indicateur, le trafic
    paraît stable alors qu'il s'effondre (rejets massifs langue:fr, etc.).
    """
    rejets: dict[str, int] = {}
    for ligne in lignes:
        if ligne.get("source") != "production":
            continue
        statut = ligne.get("status")
        if statut == 422:
            motif = str(ligne.get("motif") or "inconnu")
            rejets[motif] = rejets.get(motif, 0) + 1
        elif statut == 500:
            rejets["exception_500"] = rejets.get("exception_500", 0) + 1
    return rejets


# =============================================================================
# RÉFÉRENCE DE DÉRIVE — CSV P0 + contrôle de fraîcheur (R11)
# =============================================================================


def charger_reference() -> tuple[pd.DataFrame, str | None]:
    """Charge reference_drift.csv + vérifie le sidecar meta.json.

    Retourne (DataFrame, alerte|None). Une référence périmée (générée pour
    une autre version du modèle) ne fait pas échouer le job : la dérive
    serait fausse, on PREVIENT (warning) — la régénération est un acte humain.
    """
    df = pd.read_csv(REFERENCE_DRIFT_CSV)

    alerte: str | None = None
    try:
        meta = json.loads(REFERENCE_DRIFT_META.read_text(encoding="utf-8"))
        version_modele = json.loads(METRICS_JSON.read_text(encoding="utf-8"))["model_version"]
        if meta.get("model_version") != version_modele:
            alerte = (
                f"⚠️ Référence de dérive périmée : générée pour {meta.get('model_version')} "
                f"mais le modèle servi est {version_modele} → régénérer "
                f"(uv run python scripts/build_reference_drift.py)"
            )
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        alerte = f"⚠️ Sidecar {REFERENCE_DRIFT_META.name} illisible ({e}) — fraîcheur non vérifiée"

    if alerte:
        print(alerte)
    return df, alerte
