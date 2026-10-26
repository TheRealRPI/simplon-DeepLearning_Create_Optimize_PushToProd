"""
Barrière qualité — refuse un modèle dont les métriques sont sous les seuils.

Principe :
- config.yaml (racine du projet) définit les seuils : f1_minimum, test_size_minimum ;
- model/metrics.json contient les métriques réelles du modèle entraîné ;
- ce script échoue (exit 1) si une métrique est sous son seuil.

Seuil F1 = 0,83 car F1_test − marge_de_bruit = 0,8608 − 0,0313 = 0,8295 :
un modèle honnête garde sa marge de bruit, un modèle dégradé est refusé.

Usage :
    uv run python -m deeplearning_create_optimize_pushtoprod.quality_gate
    # Options pour tester d'autres fichiers (ex. faux modèle de la démo) :
    uv run python -m deeplearning_create_optimize_pushtoprod.quality_gate \
        --metrics faux_metrics.json

Auteur : TheRealRPI
Date   : 26/10/2026
"""

# =============================================================================
# IMPORTS
# =============================================================================

import argparse  # Pour les options --config / --metrics
import json  # Pour lire metrics.json
import sys  # Pour le code de sortie
from pathlib import Path  # Pour gérer les chemins de fichiers

import yaml  # Pour lire config.yaml

# =============================================================================
# CHEMINS PAR DÉFAUT
# =============================================================================

# Racine du projet : ce fichier est dans src/<pkg>/, on remonte de 3 niveaux
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
METRICS_PATH = PROJECT_ROOT / "model" / "metrics.json"

# =============================================================================
# FONCTION PRINCIPALE — Vérification des seuils
# =============================================================================


def verifier_qualite(
    chemin_config: Path | None = None,
    chemin_metrics: Path | None = None,
) -> tuple[bool, list[str]]:
    """
    Vérifie que metrics.json respecte les seuils de config.yaml.

    Paramètres (None = utiliser les chemins par défaut du projet) :
    - chemin_config  : fichier YAML des seuils (f1_minimum, test_size_minimum)
    - chemin_metrics : fichier JSON des métriques (f1_score_test, test_size)

    Retourne :
    - (True,  messages ✅)  si le modèle passe la barrière ;
    - (False, messages ❌)  si un seuil n'est pas respecté, un fichier
      est introuvable, malformé, ou qu'une clé manque (jamais de crash silencieux).
    """
    chemin_config = chemin_config or CONFIG_PATH
    chemin_metrics = chemin_metrics or METRICS_PATH
    messages: list[str] = []

    # -------------------------------------------------------------------------
    # 1. LIRE LES SEUILS (config.yaml)
    # -------------------------------------------------------------------------
    try:
        with open(chemin_config, encoding="UTF-8") as f:
            seuils = yaml.safe_load(f)
    except FileNotFoundError:
        return False, [f"❌ Fichier de configuration introuvable : {chemin_config}"]
    except yaml.YAMLError as e:
        return False, [f"❌ config.yaml malformé : {e}"]

    try:
        f1_minimum = float(seuils["f1_minimum"])
        test_size_minimum = int(seuils["test_size_minimum"])
    except (KeyError, TypeError, ValueError):
        return False, [
            f"❌ config.yaml doit contenir 'f1_minimum' (float) et 'test_size_minimum' (int) : {chemin_config}"
        ]

    # -------------------------------------------------------------------------
    # 2. LIRE LES MÉTRIQUES RÉELLES (metrics.json)
    # -------------------------------------------------------------------------
    try:
        with open(chemin_metrics, encoding="UTF-8") as f:
            metriques = json.load(f)
    except FileNotFoundError:
        return False, [f"❌ Fichier de métriques introuvable : {chemin_metrics}"]
    except json.JSONDecodeError as e:
        return False, [f"❌ metrics.json malformé : {e}"]

    try:
        f1_score = float(metriques["f1_score_test"])
        test_size = int(metriques["test_size"])
    except (KeyError, TypeError, ValueError):
        return False, [f"❌ metrics.json doit contenir 'f1_score_test' (float) et 'test_size' (int) : {chemin_metrics}"]

    # -------------------------------------------------------------------------
    # 3. COMPARER MÉTRIQUES ET SEUILS
    # -------------------------------------------------------------------------
    ok = True

    # --- F1 minimum ---
    if f1_score >= f1_minimum:
        messages.append(f"✅ F1 score : {f1_score:.4f} ≥ seuil {f1_minimum}")
    else:
        ok = False
        messages.append(f"❌ F1 score : {f1_score:.4f} < seuil {f1_minimum}")

    # --- Taille du jeu de test ---
    if test_size >= test_size_minimum:
        messages.append(f"✅ Taille du jeu de test : {test_size} ≥ seuil {test_size_minimum}")
    else:
        ok = False
        messages.append(f"❌ Taille du jeu de test : {test_size} < seuil {test_size_minimum}")

    return ok, messages


# =============================================================================
# POINT D'ENTRÉE — Ligne de commande
# =============================================================================


def main(argv: list[str] | None = None) -> int:
    """
    Lance la barrière qualité depuis la ligne de commande.

    Retourne :
    - 0 si le modèle est accepté ;
    - 1 sinon (refusé, fichier introuvable ou malformé).
    """
    parseur = argparse.ArgumentParser(
        description="Barrière qualité : vérifie metrics.json contre les seuils de config.yaml"
    )
    parseur.add_argument(
        "--config", type=Path, default=None, help="Chemin du fichier YAML des seuils (défaut : config.yaml à la racine)"
    )
    parseur.add_argument(
        "--metrics", type=Path, default=None, help="Chemin du fichier JSON des métriques (défaut : model/metrics.json)"
    )
    args = parseur.parse_args(argv)

    ok, messages = verifier_qualite(chemin_config=args.config, chemin_metrics=args.metrics)

    print("🚦 Barrière qualité")
    for message in messages:
        print(f"   {message}")

    if ok:
        print("🟢 MODÈLE ACCEPTÉ")
        return 0
    print("🔴 MODÈLE REFUSÉ")
    return 1


if __name__ == "__main__":
    sys.exit(main())
