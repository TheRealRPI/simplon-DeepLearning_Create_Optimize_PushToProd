"""
Tests unitaires de nettoyer_texte (preprocessing.py).

Chaque règle de nettoyage est vérifiée, ainsi que les deux invariants :
- idempotence : nettoyer deux fois = nettoyer une fois ;
- un texte déjà propre ne doit pas être modifié.

Exécution :
    uv run pytest tests/test_preprocessing.py -v
"""

from deeplearning_create_optimize_pushtoprod.preprocessing import nettoyer_texte

# =============================================================================
# ESPACEMENTS — sauts de ligne, tabulations, espaces multiples
# =============================================================================


class TestEspaces:
    """Tous les espacements doivent devenir une seule espace (règle du notebook)."""

    def test_sauts_de_ligne(self):
        """Les \\n simples et doublés → une seule espace."""
        assert nettoyer_texte("Hello\n\nworld\nend") == "Hello world end"

    def test_tabulations(self):
        """Les \\t → une seule espace."""
        assert nettoyer_texte("Hello\tworld") == "Hello world"

    def test_retour_chariot_windows(self):
        """Le \\r\\n de Windows → une seule espace."""
        assert nettoyer_texte("Hello\r\nworld") == "Hello world"

    def test_espaces_multiples_et_bords(self):
        """Espaces multiples et espaces de bord → une seule espace + strip."""
        assert nettoyer_texte("   Hello    world   ") == "Hello world"


# =============================================================================
# INVISIBLES ET CONTRÔLES — NBSP, zero-width, BOM, soft hyphen, contrôles C0/C1
# =============================================================================


class TestInvisiblesEtControles:
    """Les caractères invisibles doivent disparaître (remplacés par une espace)."""

    def test_nbsp(self):
        """L'espace insécable \\u00a0 → espace simple."""
        assert nettoyer_texte("Hello\u00a0world") == "Hello world"

    def test_zero_width_et_bom(self):
        """BOM (\\ufeff) et espace de largeur nulle (\\u200b) → espace simple."""
        assert nettoyer_texte("\ufeffHello\u200bworld") == "Hello world"

    def test_soft_hyphen(self):
        """Le soft hyphen invisible (\\u00ad) → espace simple."""
        assert nettoyer_texte("Movie\u00adnight") == "Movie night"

    def test_caractere_de_controle(self):
        """\\x07 coupe un mot en deux sans nettoyage (« ca\\x07r » → « ca r »)."""
        assert nettoyer_texte("ca\x07r crash") == "ca r crash"


# =============================================================================
# TYPOGRAPHIE — guillemets courbes, tirets, ligatures (NFKC)
# =============================================================================


class TestTypographie:
    """La typographie exotique doit être ramenée à l'ASCII."""

    def test_apostrophe_courbe(self):
        """L'apostrophe typographique « ’ » → apostrophe ASCII."""
        assert nettoyer_texte("she’s no vegan") == "she's no vegan"

    def test_guillemets_courbes(self):
        """Guillemets typographiques « “ ” » → guillemets ASCII."""
        assert nettoyer_texte("“Hello”") == '"Hello"'

    def test_tiret_cadratin(self):
        """Le tiret cadratin « — » → tiret ASCII."""
        assert nettoyer_texte("blood—moon") == "blood-moon"

    def test_ligature_nfkc(self):
        """NFKC : la ligature « ﬁ » devient « fi »."""
        assert nettoyer_texte("ﬁnancial") == "financial"


# =============================================================================
# POLLUTION WEB — balises HTML, URL, e-mails
# =============================================================================


class TestPollutionWeb:
    """Les pollutions de scraping doivent être supprimées."""

    def test_balises_html(self):
        """Les balises HTML disparaissent, le texte reste."""
        assert nettoyer_texte("<p>Hello <b>world</b></p>") == "Hello world"

    def test_url(self):
        """Une URL complète disparaît, le reste du texte reste."""
        assert nettoyer_texte("Watch https://example.com/x?id=1 now") == "Watch now"

    def test_email(self):
        """Une adresse e-mail disparaît, le reste du texte reste."""
        assert nettoyer_texte("Contact me@studio.com today") == "Contact today"


# =============================================================================
# INVARIANTS — ce qui ne doit JAMAIS changer
# =============================================================================


class TestInvariants:
    """Le nettoyage ne doit ni modifier un texte propre, ni masquer une erreur de type."""

    def test_texte_propre_inchange(self):
        """Un texte déjà propre passe à l'identique."""
        texte = "A family moves into an old mansion deep in the countryside."
        assert nettoyer_texte(texte) == texte

    def test_idempotence(self):
        """Nettoyer un texte déjà nettoyé ne doit plus rien changer."""
        bruit = "  <p>she’s\n\nno\u00a0vegan</p>\t— \ufeffok  "
        une_fois = nettoyer_texte(bruit)
        assert nettoyer_texte(une_fois) == une_fois

    def test_entree_non_str_renvoyee_telle_quelle(self):
        """Un non-string (ex: 42) passe tel quel → Pydantic gère l'erreur de type."""
        assert nettoyer_texte(42) == 42

    def test_texte_vide(self):
        """Le texte vide reste vide."""
        assert nettoyer_texte("") == ""

    def test_texte_reduit_a_rien(self):
        """Espaces + invisibles seuls → il ne reste rien (l'API rejettera en 422)."""
        assert nettoyer_texte(" \n\t\u200b\ufeff ") == ""
