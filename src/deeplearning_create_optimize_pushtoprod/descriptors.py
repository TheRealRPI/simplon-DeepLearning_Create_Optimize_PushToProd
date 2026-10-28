"""
Descripteurs de texte pour le monitoring des prédictions.

Pourquoi ce module (plan monitoring §5.1) :
le signal principal de dérive est `oov_rate` — la part de tokens du texte
absents du vocabulaire TF-IDF (9 005 termes). Si ce taux monte, les
utilisateurs emploient un vocabulaire que le modèle n'a jamais vu.

Contrat (A1 : aucune dépendance nouvelle dans l'image de service) :
- stdlib + langdetect (déjà dans requirements.txt) — RIEN d'autre ;
- aucune fonction ne lève : un descripteur ne doit jamais casser une requête ;
- `oov_rate` reçoit `analyze` et `vocab` de l'APPELANT (api.py) : ce module
  n'importe pas model_loader → testable isolément, sans modèle ;
- le `texte` reçu est DÉJÀ NETTOYÉ (nettoyer_texte en mode="before") : les
  descripteurs décrivent ce que voit le vectoriseur, pas l'entrée brute.

Règle d'or oov_rate (§5.1) :
utiliser `vectorizer.build_analyzer()` — jamais une tokenisation maison.
C'est le seul moyen de garantir lowercase / token_pattern / ngram_range(1,2)
IDENTIQUES à l'entraînement.

Auteur : TheRealRPI
Date   : 28/10/2026
"""

# =============================================================================
# IMPORTS
# =============================================================================

from langdetect import LangDetectException, detect

# =============================================================================
# DESCRIPTIEURS — tous non levants
# =============================================================================


def longueur(texte: str) -> int:
    """Nombre de caractères du texte (déjà nettoyé)."""
    return len(texte)


def nb_mots(texte: str) -> int:
    """Nombre de mots du texte (découpe sur les espaces)."""
    return len(texte.split())


def langue(texte: str) -> str:
    """Langue détectée ("en", "fr"...), "unknown" si la détection échoue.

    Ne lève JAMAIS : un texte vide ou du bruit font échouer langdetect,
    un descripteur ne doit pas casser la requête pour autant.
    """
    try:
        return detect(texte)
    except (LangDetectException, Exception):  # pragma: no cover - filet de sécurité
        return "unknown"


def oov_rate(texte: str, analyze, vocab: set[str]) -> float:
    """Part de tokens absents du vocabulaire TF-IDF, dans [0, 1].

    Args:
        texte   : texte DÉJÀ NETTOYÉ (celui vu par le vectoriseur)
        analyze : `vectorizer.build_analyzer()` fourni par l'appelant
        vocab   : `set(vectorizer.vocabulary_)` fourni par l'appelant

    Le signal : si le taux monte, les utilisateurs emploient un vocabulaire
    que le modèle n'a jamais vu pendant l'entraînement → dérive d'entrées.

    Texte sans tokens → 0.0 (aucun token hors vocabulaire parmi aucun token).
    """
    tokens = analyze(texte)
    if not tokens:
        return 0.0
    connus = sum(1 for token in tokens if token in vocab)
    return 1.0 - connus / len(tokens)
