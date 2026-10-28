"""
Baseline du golden set — rejoue les 400 lignes de model/reference.csv sur l'API
(Phase 0 du plan monitoring) et mesure le F1 / accuracy réellement servis.

Pourquoi ce script :
le golden set est tiré de y_test ET y_prod (les deux held-out), donc le F1 mesuré
ici n'est PAS f1_score_test (0,8571 — test seul). On mesure puis on FIGE la
valeur : c'est elle qui servira de point de comparaison au monitoring
(f1_reference_golden_set), pas f1_score_test.

Convention (plan §4.1) :
une ligne qui renvoie une erreur (422, 500, réseau) compte comme une ERREUR de
prédiction (classe prédite = inverse de la cible), jamais comme un skip —
sinon le F1 serait optimiste.

Critère d'acceptation : F1 ∈ [0, 84 ; 0, 88] (IC95 ≈ ±2,5 points à n = 400).

Usage :
    uv run uvicorn deeplearning_create_optimize_pushtoprod.api:app --port 8000 &
    uv run python scripts/check_golden_set.py
    # ou : API_URL=http://hote:port uv run python scripts/check_golden_set.py

Sortie : affichage + reports/golden_set_baseline.json
Codes de sortie : 0 = conforme · 1 = F1 hors intervalle · 3 = API injoignable

Auteur : TheRealRPI
Date   : 28/10/2026
"""

# =============================================================================
# IMPORTS
# =============================================================================

import json
from datetime import UTC, datetime
from os import getenv
from pathlib import Path

import httpx
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

# =============================================================================
# CHEMINS & CONSTANTES
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
REFERENCE_CSV = PROJECT_ROOT / "model" / "reference.csv"
REPORTS_DIR = PROJECT_ROOT / "reports"
BASELINE_JSON = REPORTS_DIR / "golden_set_baseline.json"

API_URL = getenv("API_URL", "http://localhost:8000")
TIMEOUT_S = 15.0

# Intervalle d'acceptation du plan (§4.1) : F1 ∈ [0, 84 ; 0, 88] à n = 400
F1_MIN, F1_MAX = 0.84, 0.88

# En-tête ignoré par l'API aujourd'hui, exploité par le mode golden set (Phase 1) :
# envoyer dès maintenant garantit que les lignes de ce rejeu ne seront jamais
# comptées comme du trafic de production dans les logs.
HEADERS = {"X-Monitoring-Source": "golden_set"}


# =============================================================================
# REJEU DES 400 LIGNES
# =============================================================================


def rejouer_golden_set() -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Rejoue les 400 lignes du golden set sur l'API.

    Retourne :
    - un DataFrame (cible, prediction, statut) ;
    - un compteur d'erreurs par statut ("422", "500", "reseau"...).
    """
    df = pd.read_csv(REFERENCE_CSV)
    lignes: list[dict] = []
    erreurs: dict[str, int] = {}

    with httpx.Client(base_url=API_URL, timeout=TIMEOUT_S, headers=HEADERS) as client:
        for i, row in df.iterrows():
            resume = str(row["resume"])
            cible = int(row["cible"])

            try:
                reponse = client.post("/predict", json={"texte": resume})
                statut = reponse.status_code
                if statut == 200:
                    proba = float(reponse.json()["probabilite"])
                    # L'API renvoie classe: "1 : horreur" (string) — on recalcule
                    # depuis la probabilité, on ne parse jamais la chaîne.
                    prediction = 1 if proba > 0.5 else 0
                else:
                    # 422 / 5xx : erreur de prédiction, jamais un skip
                    prediction = 1 - cible
                    erreurs[str(statut)] = erreurs.get(str(statut), 0) + 1
            except httpx.HTTPError:
                statut = 0
                prediction = 1 - cible
                erreurs["reseau"] = erreurs.get("reseau", 0) + 1

            lignes.append({"cible": cible, "prediction": prediction, "statut": statut})
            if (i + 1) % 100 == 0:
                print(f"   … {i + 1}/{len(df)} lignes rejouées")

    return pd.DataFrame(lignes), erreurs


# =============================================================================
# PROGRAMME PRINCIPAL
# =============================================================================


def main() -> int:
    # --- 1) L'API doit être joignable ----------------------------------------
    try:
        sante = httpx.get(f"{API_URL}/health", timeout=TIMEOUT_S)
        sante.raise_for_status()
        infos = sante.json()
    except httpx.HTTPError:
        print(f"❌ API injoignable sur {API_URL}")
        print("   La démarrer d'abord :")
        print("   uv run uvicorn deeplearning_create_optimize_pushtoprod.api:app --port 8000")
        return 3

    # --- 2) Rejeu ------------------------------------------------------------
    print(f"▶️  Rejeu du golden set ({REFERENCE_CSV.name}) sur {API_URL}")
    resultats, erreurs = rejouer_golden_set()

    # --- 3) Métriques ---------------------------------------------------------
    y_vrai = resultats["cible"]
    y_pred = resultats["prediction"]

    f1 = float(f1_score(y_vrai, y_pred))  # binaire, classe positive = 1 (horreur)
    acc = float(accuracy_score(y_vrai, y_pred))
    tn, fp, fn, tp = confusion_matrix(y_vrai, y_pred, labels=[0, 1]).ravel()
    conforme = F1_MIN <= f1 <= F1_MAX

    # --- 4) Affichage ----------------------------------------------------------
    print()
    print("=" * 60)
    print("BASELINE GOLDEN SET (400 lignes)")
    print("=" * 60)
    print(f"  F1           : {f1:.4f}   (acceptation [{F1_MIN} ; {F1_MAX}])")
    print(f"  Accuracy     : {acc:.4f}")
    print(f"  Matrice      : TN={tn}  FP={fp}  FN={fn}  TP={tp}")
    print(f"  Erreurs      : {erreurs or 'aucune'}")
    print(f"  Modèle       : {infos.get('version')} · image {infos.get('version_image')}")
    print("  ⚠️  Ce F1 n'est PAS f1_score_test (0,8571, test seul)")
    if conforme:
        print(f"  ✅ Conforme → figer f1_reference_golden_set = {f1:.4f}")
    else:
        print("  ❌ Hors intervalle → NE PAS figer, investiguer (plan §4.1, R2)")
    print("=" * 60)

    # --- 5) Artefact figé -------------------------------------------------------
    rapport = {
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "api_url": API_URL,
        "model_version": infos.get("version"),
        "image_version": infos.get("version_image"),
        "n": len(resultats),
        "f1": round(f1, 4),
        "accuracy": round(acc, 4),
        "matrice_confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "erreurs": erreurs,
        "intervalle_acceptation": [F1_MIN, F1_MAX],
        "conforme": conforme,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(BASELINE_JSON, "w", encoding="utf-8") as f:
        json.dump(rapport, f, indent=2, ensure_ascii=False)
    print(f"\n📝 Baseline écrite : {BASELINE_JSON}")

    return 0 if conforme else 1


if __name__ == "__main__":
    raise SystemExit(main())
