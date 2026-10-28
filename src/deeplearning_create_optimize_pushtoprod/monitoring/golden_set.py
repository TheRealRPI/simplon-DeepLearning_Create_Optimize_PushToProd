"""
Rejeu du golden set (400 lignes) sur l'API déployée → F1 réellement servi.

D3 : mesurer l'ARTEFACT réellement servi (preprocessing + vectoriseur +
quantification), pas une copie locale du modèle. Le rejeu passe par HTTP
avec l'en-tête X-Monitoring-Source: golden_set — ces lignes sont loguées
mais exclues du trafic production (filtre collect.py).

Conventions (héritées de scripts/check_golden_set.py, P0) :
- la classe est recalculée depuis `probabilite > 0.5` — l'API renvoie
  classe "1 : horreur" (string), on ne parse JAMAIS la chaîne (M7) ;
- une ligne qui échoue (422, 5xx, réseau après retries) compte comme une
  ERREUR de prédiction (classe = inverse de la cible), jamais comme un skip
  — sinon le F1 est optimiste ;
- un 422 est déterministe : pas de retry. Un 5xx/réseau : 2 tentatives.

Comparaisons :
- f1_minimum (0.83) : le seuil d'ALERTE → non conforme = régression ;
- f1_reference_golden_set (0.8713, baseline P0) : l'écart est rapporté
  à titre diagnostic (régression d'artefact vs dérive des données).

Échec réseau complet → APIInjoignable → code de sortie 3.

Auteur : TheRealRPI
Date   : 28/10/2026
"""

# =============================================================================
# IMPORTS
# =============================================================================

import json
from pathlib import Path

import httpx
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

from .drift import REPORTS_DIR, rapport_classification

# =============================================================================
# CONSTANTES
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_CSV = PROJECT_ROOT / "model" / "reference.csv"

HEADERS = {"X-Monitoring-Source": "golden_set"}
NB_TENTATIVES = 2   # 5xx / réseau uniquement — un 422 est déterministe
TIMEOUT_S = 15.0


# =============================================================================
# ERREURS
# =============================================================================


class APIInjoignable(Exception):
    """L'API ne répond pas → le job sort en code 3 (rouge, pas d'alerte modèle)."""


# =============================================================================
# REJEU D'UNE LIGNE
# =============================================================================


def _rejouer_ligne(client: httpx.Client, resume: str, cible: int) -> dict:
    """Une ligne du golden set → {classe, statut, proba}.

    Échec après NB_TENTATIVES → classe = inverse de la cible (erreur assumée).
    """
    for _ in range(NB_TENTATIVES):
        try:
            reponse = client.post("/predict", json={"texte": resume}, headers=HEADERS)
        except httpx.HTTPError:
            continue  # réseau : nouvelle tentative
        if reponse.status_code == 200:
            proba = float(reponse.json()["probabilite"])
            return {"classe": 1 if proba > 0.5 else 0, "statut": 200, "proba": proba}
        if reponse.status_code == 422:
            # Rejet de validation déterministe : erreur de prédiction, pas de retry
            return {"classe": 1 - cible, "statut": 422, "proba": None}
        # 5xx : le serveur a un problème → nouvelle tentative
    # Réseau épuisé : erreur de prédiction
    return {"classe": 1 - cible, "statut": 0, "proba": None}


# =============================================================================
# VÉRIFICATION PRÉALABLE DE L'API
# =============================================================================


def verifier_api(client: httpx.Client) -> dict:
    """/health → infos (version modèle, version image). Lève APIInjoignable sinon."""
    try:
        reponse = client.get("/health")
        reponse.raise_for_status()
        return reponse.json()
    except httpx.HTTPError as e:
        raise APIInjoignable(f"/health injoignable : {e}") from e


# =============================================================================
# REJEU COMPLET + MÉTRIQUES + RAPPORT
# =============================================================================


def rejouer_et_rapporter(
    client: httpx.Client, parametres: dict, horodatage: str
) -> dict:
    """Rejoue les 400 lignes, calcule F1/accuracy, écrit le rapport JSON.

    Retourne : {f1, accuracy, n, n_422, n_erreurs, conforme, ecart_vs_reference,
                version_modele, version_image, matrice_confusion}
    """
    df = pd.read_csv(REFERENCE_CSV)
    print(f"▶️  Rejeu du golden set : {len(df)} lignes")

    lignes: list[dict] = []
    for i, row in df.iterrows():
        cible = int(row["cible"])
        resultat = _rejouer_ligne(client, str(row["resume"]), cible)
        lignes.append({"cible": cible, **resultat})
        if (i + 1) % 100 == 0:
            print(f"   … {i + 1}/{len(df)} lignes rejouées")

    resultats = pd.DataFrame(lignes)
    n_422 = int((resultats["statut"] == 422).sum())
    n_erreurs = int((resultats["statut"] != 200).sum())

    f1 = float(f1_score(resultats["cible"], resultats["classe"]))  # classe positive = 1 (horreur)
    accuracy = float(accuracy_score(resultats["cible"], resultats["classe"]))
    tn, fp, fn, tp = confusion_matrix(resultats["cible"], resultats["classe"], labels=[0, 1]).ravel()

    f1_minimum = float(parametres["f1_minimum"])
    f1_reference = float(parametres["f1_reference_golden_set"])
    conforme = f1 >= f1_minimum
    ecart = round(f1 - f1_reference, 4)

    rapport = {
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "n": len(resultats),
        "n_422": n_422,
        "n_erreurs": n_erreurs,
        "matrice_confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "conforme": conforme,
        "f1_minimum": f1_minimum,
        "f1_reference_golden_set": f1_reference,
        "ecart_vs_reference": ecart,
    }

    # Écriture du rapport JSON (§6.3 : reports/golden_set_<date>.json)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    chemin = REPORTS_DIR / f"golden_set_{horodatage}.json"
    chemin.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    rapport["rapport_json"] = str(chemin)

    # Rapport Evidently de classification (visualisation du golden set — §6.2) :
    # Accuracy/F1/Precision/Recall sur les prédictions REUSSIES ; les échecs,
    # déjà comptés comme prédictions fausses ci-dessus, ne sont pas représentables.
    rapport["rapport_classification_html"] = str(
        rapport_classification(resultats[["cible", "classe"]], horodatage)
    )

    print(f"   F1 = {f1:.4f} (référence {f1_reference} · minimum {f1_minimum} · écart {ecart:+.4f})")
    print(f"   Erreurs : {n_erreurs} dont {n_422} rejets 422")

    return rapport
