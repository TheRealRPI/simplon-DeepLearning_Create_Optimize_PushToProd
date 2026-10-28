"""
Nettoyage du texte en entrée de l'API — aligné sur l'entraînement.

Fournit nettoyer_texte(), appelé par POST /predict AVANT la validation :
le texte reçu (sauts de ligne, caractères invisibles, HTML, typographie
exotique...) est ramené à la forme des résumés vus pendant l'entraînement
(notebook, cellule 7 : strip + espaces multiples → espace simple).

Volontairement ABSENT du nettoyage (testé contre le vrai vectoriseur) :
- les stopwords : le vectoriseur TF-IDF les retire déjà (stop_words="english") ;
- les accents : le vocabulaire d'entraînement contient des mots accentués
  (« cafè », « fiancèe »...), les retirerait créerait des tokens inconnus ;
- la ponctutation : le motif de tokenisation (?u)\\b\\w\\w+\\b l'ignore déjà.

Auteur : TheRealRPI
Date   : 28/10/2026
"""

# =============================================================================
# IMPORTS
# =============================================================================

import re  # Pour les expressions régulières de nettoyage
import unicodedata  # Pour la normalisation Unicode NFKC

# =============================================================================
# RÈGLES DE NETTOYAGE — compilées une seule fois au chargement du module
# =============================================================================

# Guillemets et tirets typographiques → équivalents ASCII
# (NFKC ne les convertit PAS : « she’s » garderait son apostrophe U+2019)
_TRADUCTIONS = str.maketrans(
    {
        "’": "'",  # apostrophe typographique droite
        "‘": "'",  # apostrophe typographique gauche
        "‚": "'",  # guillemet-virgule inférieur
        "‛": "'",  # apostrophe haute inversée
        "“": '"',  # guillemet typographique ouvrant
        "”": '"',  # guillemet typographique fermant
        "„": '"',  # guillemet-virgule inférieur
        "–": "-",  # tiret demi-cadratin
        "—": "-",  # tiret cadratin
        "‒": "-",  # tiret numérique
        "―": "-",  # tiret horizontal
    }
)

# Balises HTML (<p>, <br/>, </div>...) — pollutions fréquentes de textes scrapés du web
_BALISES_HTML = re.compile(r"<[^>]+>")
# URL complètes (http/https/www) — aucun intérêt pour classifier un résumé
_URLS = re.compile(r"https?://\S+|www\.\S+")
# Adresses e-mail
_EMAILS = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# Caractères de contrôle et invisibles (hors \t et \n, simples séparateurs
# d'espacement que la règle \s+ ci-dessous ramène de toute façon à une espace) :
#   \x00-\x08        contrôles C0 (ex: \x07 « bell ») — les seuls capables de
#                    CASSER un mot : « ca\x07r » devient « ca r » sans nettoyage
#   \x0b-\x1f        contrôles C0 (dont \r, ramené à une espace)
#   \x7f-\x9f        contrôles C1
#   \u00ad           soft hyphen (trait d'union invisible)
#   \u200b-\u200f    espaces de largeur nulle + marques directionnelles
#   \ufeff           BOM / espace insécable de largeur nulle
_INVISIBLES = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u00ad\u200b-\u200f\ufeff]")

# Tous les espacements (dont \n, \t, NBSP) → une seule espace —
# LA règle du notebook d'entraînement (cellule 7) :
#   df[colonne_resume].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
_ESPACES = re.compile(r"\s+")


# =============================================================================
# FONCTION PRINCIPALE — nettoyage d'une entrée
# =============================================================================


def nettoyer_texte(texte: str) -> str:
    """
    Nettoie le texte reçu par POST /predict, avant la validation et l'inférence.

    Ordre des étapes :
    1. Normalisation Unicode NFKC (ligatures « ﬁ » → « fi », « … » → « ... ») ;
    2. Typographie → ASCII (apostrophes/guillemets courbes, tirets) ;
    3. Balises HTML, URL, e-mails → espace ;
    4. Caractères de contrôle et invisibles → espace ;
    5. Tous les espacements → une seule espace + strip (règle du notebook).

    Args:
        texte: le résumé brut envoyé par le client

    Returns:
        str: le texte normalisé, prêt pour langdetect et le vectoriseur TF-IDF.
             Une entrée non-chaîne (ex: 42) est renvoyée TELLE QUELLE pour que
             Pydantic produise son erreur 422 de type habituelle.
    """
    # Garde-fou : ne pas nettoyer une entrée non-chaîne,
    # Pydantic la rejettera avec son erreur de type (test test_texte_mauvais_type)
    if not isinstance(texte, str):
        return texte

    # 1. Normalisation Unicode (formes de compatibilité → équivalents simples)
    texte = unicodedata.normalize("NFKC", texte)

    # 2. Typographie → ASCII
    texte = texte.translate(_TRADUCTIONS)

    # 3. Pollutions web → espace
    texte = _BALISES_HTML.sub(" ", texte)
    texte = _URLS.sub(" ", texte)
    texte = _EMAILS.sub(" ", texte)

    # 4. Contrôles + invisibles → espace
    texte = _INVISIBLES.sub(" ", texte)

    # 5. Règle du notebook d'entraînement : espacements multiples → une espace
    texte = _ESPACES.sub(" ", texte)

    return texte.strip()
