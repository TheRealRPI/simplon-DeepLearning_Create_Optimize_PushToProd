"""
Orchestrateur du job de monitoring — CLI + codes de sortie (plan §6.4/§6.5).

Usage :
    python -m deeplearning_create_optimize_pushtoprod.monitoring \
        [--no-mlflow] [--api-url URL]

Env : API_URL · PREDICTIONS_LOG · MONITORING_REPORTS_DIR

Codes de sortie :
    0  sain                   → CI verte
    1  dérive OU F1 < seuil   → rouge / alerte
    2  données insuffisantes  → neutre (warning) — 3 requêtes ne font pas une dérive
    3  API injoignable        → rouge

Table de décision (§6.5 — c'est ELLE qui répond au brief : elle doit figurer
dans MONITORING.md ET dans la soutenance, pas seulement ici) :

    dérive  golden set  diagnostic                    action
    non     conforme    sain                          rien
    non     régression  artefact déployé cassé        rollback, PAS réentraînement
    oui     conforme    les données changent          rafraîchir le jeu d'entraînement
    oui     régression  dégradation réelle            réentraînement

Auteur : TheRealRPI
Date   : 28/10/2026
"""

# =============================================================================
# IMPORTS
# =============================================================================

import argparse
from datetime import datetime
from os import getenv

import httpx

from . import collect, drift, golden_set

# =============================================================================
# PROGRAMME PRINCIPAL
# =============================================================================


def main() -> int:
    parseur = argparse.ArgumentParser(
        prog="python -m deeplearning_create_optimize_pushtoprod.monitoring",
        description="Job de monitoring du modèle : dérive des entrées + rejeu du golden set",
    )
    parseur.add_argument(
        "--no-mlflow",
        action="store_true",
        help="désactiver le tracking MLflow (D7 : la CI ne doit pas en dépendre)",
    )
    parseur.add_argument(
        "--api-url",
        default=getenv("API_URL", "http://localhost:8000"),
        help="URL de l'API à surveiller (défaut : env API_URL ou http://localhost:8000)",
    )
    arguments = parseur.parse_args()

    horodatage = datetime.now().strftime("%Y-%m-%d_%H%M")
    print("=" * 60)
    print(f"JOB DE MONITORING — {horodatage}")
    print("=" * 60)

    # --- 1) Données : logs production, rejets, référence ---------------------
    parametres = collect.charger_parametres()
    lignes, _corrompues = collect.charger_jsonl()
    production = collect.charger_production(lignes, int(parametres["fenetre_jours"]))
    rejets = collect.charger_rejets(lignes)
    reference, _alerte_reference = collect.charger_reference()

    print(f"Trafic production (fenêtre {parametres['fenetre_jours']} j) : {len(production)} lignes")
    print(f"Rejets : {rejets or 'aucun'}")

    # --- 2) Golden set : l'API doit répondre, sinon code 3 --------------------
    try:
        with httpx.Client(base_url=arguments.api_url, timeout=golden_set.TIMEOUT_S) as client:
            infos = golden_set.verifier_api(client)
            print(f"API : {arguments.api_url} (modèle {infos.get('version')} · image {infos.get('version_image')})")
            golden = golden_set.rejouer_et_rapporter(client, parametres, horodatage)
    except golden_set.APIInjoignable as e:
        print(f"❌ {e}")
        print("→ code de sortie 3 (API injoignable)")
        return 3

    # --- 3) Dérive (si assez de données, sinon garde-fou) ----------------------
    derive: bool | None = None
    if len(production) < int(parametres["fenetre_min_lignes"]):
        print(
            f"⚠️ Données insuffisantes ({len(production)} < {parametres['fenetre_min_lignes']}) "
            f": pas d'analyse de dérive, exit 2 (neutre)"
        )
    else:
        resultat_drift = drift.analyser_derive(
            production,
            reference,
            float(parametres["drift_share_max"]),
            float(parametres["oov_rate_max"]),
            float(parametres["value_drift_seuil"]),
            horodatage,
        )
        derive = resultat_drift["derive"]
        colonnes = resultat_drift["resume"]["colonnes_derivees"] or "aucune"
        share = resultat_drift["resume"]["share_calibre"]
        print(
            f"Dérive : {'⚠️ détectée' if derive else 'non'} "
            f"(colonnes au-delà du seuil : {colonnes} · share calibré : {share})"
        )
        print(f"Rapport : {resultat_drift['rapport_html']}")

    # --- 4) Diagnostic — la table de décision (§6.5) ---------------------------
    regression = not golden["conforme"]
    print()
    print("Diagnostic (table §6.5) :")
    if derive and regression:
        print("  ⛔ dérive + régression → RÉENTRAÎNEMENT")
    elif regression:
        print("  ⛔ régression SANS dérive → ARTEFACT DÉPLOYÉ CASSÉ → rollback (pas réentraînement)")
    elif derive:
        print("  ⚠️ dérive SANS régression → les données changent, le modèle tient → rafraîchir l'entraînement")
    else:
        print("  ✅ sain")

    # --- 5) MLflow (P4, D7 : optionnel, jamais requis en CI) -------------------
    if arguments.no_mlflow:
        print("Tracking MLflow : désactivé (--no-mlflow)")
    else:
        print("Tracking MLflow : pas encore branché (P4 → registry.py) ; utiliser --no-mlflow en attendant")

    # --- 6) Code de sortie (priorité 3 > 1 > 2 > 0) ------------------------------
    if regression or derive:
        return 1
    if derive is None:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
