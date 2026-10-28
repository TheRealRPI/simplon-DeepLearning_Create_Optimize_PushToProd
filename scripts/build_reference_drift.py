"""
Distribution de référence pour la dérive (Phase 0 du plan monitoring).

Calcule sur les 2 400 lignes de Data/textes_films_horreur_comedie.csv, APRÈS
nettoyer_texte() — les descripteurs décrivent ce que voit le vectoriseur, pas
l'entrée brute (règle §5.1 du plan), sinon la référence et la production ne
décriraient pas les mêmes textes :

- longueur : nombre de caractères du texte nettoyé
- nb_mots  : nombre de mots (découpe sur espaces) du texte nettoyé
- oov_rate : part de tokens absents du vocabulaire TF-IDF (9 005 termes),
             via vectorizer.build_analyzer() — jamais une tokenisation maison
- cible    : étiquette réelle (0 = comédie, 1 = horreur)
- proba    : sortie du modèle TFLite via model_loader.predict() — référence
             indispensable pour ValueDrift(column="proba") (§6.2 du plan)

Sorties :
- model/reference_drift.csv     (~100 Ko, sans texte brut)
- model/reference_drift.meta.json : model_version + date — le job de monitoring
  émet un warning si la référence est périmée (model_version ≠ metrics.json).

⚠️ Les définitions de descripteurs devront rester alignées sur
src/…/descriptors.py (Phase 1) : régénérer ce CSV après création du module.

Usage :
    uv run python scripts/build_reference_drift.py

Auteur : TheRealRPI
Date   : 28/10/2026
"""

# =============================================================================
# IMPORTS
# =============================================================================

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from deeplearning_create_optimize_pushtoprod.model_loader import model_loader
from deeplearning_create_optimize_pushtoprod.preprocessing import nettoyer_texte

# =============================================================================
# CHEMINS
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
DATA_CSV = PROJECT_ROOT / "Data" / "textes_films_horreur_comedie.csv"
SORTIE_CSV = PROJECT_ROOT / "model" / "reference_drift.csv"
SORTIE_META = PROJECT_ROOT / "model" / "reference_drift.meta.json"

# =============================================================================
# DESCRIPTIEURS
# =============================================================================
# ⚠️ Ces définitions doivent rester identiques à src/…/descriptors.py (Phase 1).
# Le vectoriseur et le vocabulaire viennent du model_loader déjà chargé :
# l'ensemble des 9 005 termes est construit UNE SEULE FOIS (jamais par ligne).


def oov_rate(texte: str, analyze, vocab: set[str]) -> float:
    """Part de tokens (unigrams + bigrams) absents du vocabulaire, dans [0, 1]."""
    tokens = analyze(texte)
    if not tokens:
        return 0.0
    connus = sum(1 for t in tokens if t in vocab)
    return 1.0 - connus / len(tokens)


# =============================================================================
# PROGRAMME PRINCIPAL
# =============================================================================


def main() -> int:
    df = pd.read_csv(DATA_CSV)
    print(f"▶️  {len(df)} lignes lues depuis {DATA_CSV.name}")

    # build_analyzer() garantit lowercase / token_pattern / ngram_range(1,2)
    # IDENTIQUES à l'entraînement — c'est le contrat du plan §5.1.
    analyze = model_loader.vectoriseur.build_analyzer()
    vocab = set(model_loader.vectoriseur.vocabulary_)
    print(f"   Vocabulaire TF-IDF : {len(vocab)} termes")

    lignes: list[dict] = []
    for i, row in df.iterrows():
        # Le texte est nettoyé AVANT tout calcul : les descripteurs décrivent
        # ce que voit le vectoriseur (et le modèle), pas le CSV brut.
        texte = nettoyer_texte(str(row["resume"]))
        proba = model_loader.predict(texte)
        lignes.append(
            {
                "longueur": len(texte),
                "nb_mots": len(texte.split()),
                "oov_rate": round(oov_rate(texte, analyze, vocab), 4),
                "cible": int(row["cible"]),
                "proba": round(proba, 4),
            }
        )
        if (i + 1) % 600 == 0:
            print(f"   … {i + 1}/{len(df)} lignes traitées")

    # --- Écriture du CSV (sans texte brut) ------------------------------------
    out = pd.DataFrame(lignes)
    SORTIE_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(SORTIE_CSV, index=False)
    print(f"\n✅ Référence écrite : {SORTIE_CSV} ({len(out)} lignes)")

    # --- Sidecar de versionnement (R11 : détecter une référence périmée) ------
    meta = {
        "model_version": model_loader.metrics["model_version"],
        "date_generation": date.today().isoformat(),
        "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_lignes": len(out),
        "source": str(DATA_CSV.name),
        "vocabulaire_size": len(vocab),
        "note": "Régénérer après chaque réentraînement (ou changement de nettoyer_texte)",
    }
    with open(SORTIE_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"✅ Sidecar écrit : {SORTIE_META} (model_version={meta['model_version']})")

    # --- Résumé de contrôle ------------------------------------------------------
    print()
    print("Distribution de référence (moyenne ± écart-type) :")
    for col in ("longueur", "nb_mots", "oov_rate", "proba"):
        print(f"  {col:<10}: {out[col].mean():.4f} ± {out[col].std():.4f}  "
              f"[min {out[col].min():.4f} · max {out[col].max():.4f}]")
    print(f"  cible      : {int(out['cible'].sum())} horreur / {int((1 - out['cible']).sum())} comédie")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
