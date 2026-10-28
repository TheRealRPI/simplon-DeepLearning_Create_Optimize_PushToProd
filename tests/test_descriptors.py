"""
Tests des descripteurs de texte (plan monitoring §5.6).

Fonctions PURES : aucune dépendance au modèle ni à l'API — `analyze` et
`vocab` sont des faux fournis par les tests, le module est testable
isolément (c'est le contrat de descriptors.py).

Exécution :
    uv run pytest tests/test_descriptors.py
"""

from deeplearning_create_optimize_pushtoprod.descriptors import langue, longueur, nb_mots, oov_rate

# =============================================================================
# FAUX VECTORISEUR — analyzer et vocab de substitution
# =============================================================================

# Imite build_analyzer() : liste de tokens (ici, découpe simple en minuscules)
FAUX_ANALYZE = str.lower


def faux_analyze(texte: str) -> list[str]:
    return texte.lower().split()


FAUX_VOCAB = {"horror", "movie", "the", "a", "family", "comedy"}

# Texte anglais de référence pour la détection de langue
TEXTE_ANGLAIS = (
    "The quick brown fox jumps over the lazy dog near the river bank while "
    "the children play outside and laugh about the comedy movie they watched."
)


# =============================================================================
# longueur / nb_mots
# =============================================================================


class TestLongueur:
    def test_texte_simple(self):
        assert longueur("abc") == 3

    def test_texte_vide(self):
        assert longueur("") == 0

    def test_espaces_comptes(self):
        assert longueur("a b") == 3


class TestNbMots:
    def test_trois_mots(self):
        assert nb_mots("un deux trois") == 3

    def test_texte_vide(self):
        assert nb_mots("") == 0

    def test_espaces_multiples(self):
        assert nb_mots("  a   b  ") == 2


# =============================================================================
# oov_rate — le signal principal de dérive
# =============================================================================


class TestOovRate:
    def test_vocabulaire_entierement_connu(self):
        """Un texte composé uniquement de vocabulaire connu → oov_rate = 0."""
        texte = "a horror movie the family"
        assert oov_rate(texte, faux_analyze, FAUX_VOCAB) == 0.0

    def test_vocabulaire_entierement_inconnu(self):
        """Un texte totalement inconnu → oov_rate = 1."""
        texte = "zzzxxx yyywww vvvuuu"
        assert oov_rate(texte, faux_analyze, FAUX_VOCAB) == 1.0

    def test_fraction_exacte(self):
        """1 token connu sur 2 → oov_rate = 0.5."""
        assert oov_rate("horror zzzxxx", faux_analyze, FAUX_VOCAB) == 0.5

    def test_texte_vide_sans_exception(self):
        """Aucun token → 0.0, jamais d'exception (contrat du module)."""
        assert oov_rate("", faux_analyze, FAUX_VOCAB) == 0.0

    def test_bornes_0_1(self):
        """Quel que soit le texte, le résultat reste dans [0, 1]."""
        textes = ["", "a", "zzz", "the horror movie zzz xxx", "HORROR Movie"]
        for texte in textes:
            taux = oov_rate(texte, faux_analyze, FAUX_VOCAB)
            assert 0.0 <= taux <= 1.0, f"oov_rate hors bornes pour {texte!r} : {taux}"

    def test_analyzer_bien_utilise(self):
        """Les tokens viennent de analyze(), pas d'une tokenisation maison :
        ici analyze passe en minuscules → 'HORROR' est reconnu."""
        assert oov_rate("HORROR", faux_analyze, FAUX_VOCAB) == 0.0


# =============================================================================
# langue — jamais levante
# =============================================================================


class TestLangue:
    def test_anglais(self):
        assert langue(TEXTE_ANGLAIS) == "en"

    def test_echec_ne_leve_pas(self):
        """Texte sans aucune langue détectable → "unknown", pas d'exception."""
        assert langue("1234567890 !!!! ????? ####") == "unknown"

    def test_texte_vide_ne_leve_pas(self):
        assert langue("") == "unknown"
