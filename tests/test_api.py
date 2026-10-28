"""
Tests automatisés de l'API FastAPI — Classification horreur vs comédie.

Routes testées :
- GET  /           : page d'accueil
- GET  /health     : vérification de santé
- GET  /v1/models  : liste des modèles
- POST /predict    : prédiction (succès, erreurs 422, erreur 500)

Exécution :
    uv run pytest

Le vrai modèle TFLite est utilisé pour les prédictions (test de bout en bout).
Seul le test d'erreur 500 utilise un mock (impossible à déclencher autrement).
"""

import re

import pytest

# =============================================================================
# GET / — Page d'accueil
# =============================================================================


class TestRoot:
    """Tests de la route GET /."""

    def test_statut_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_contenu(self, client):
        response = client.get("/")
        data = response.json()
        assert data["message"] == "Bienvenue sur l'API"
        assert data["doc"] == "/docs"
        assert data["health"] == "/health"


# =============================================================================
# GET /health — Vérification de santé
# =============================================================================


class TestHealth:
    """Tests de la route GET /health."""

    def test_statut_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_status_ok(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_infos_modele_presentes(self, client):
        """Le /health doit exposer les infos du modèle."""
        data = client.get("/health").json()
        for cle in ("version", "type", "runtime", "f1_score"):
            assert cle in data, f"Clé manquante dans /health : {cle}"

    def test_infos_coherentes_avec_metrics(self, client):
        """Les infos exposées doivent correspondre à metrics.json."""
        data = client.get("/health").json()
        assert data["type"] == "tflite"
        assert data["runtime"] == "liteRT"
        assert isinstance(data["f1_score"], float)
        assert 0.0 <= data["f1_score"] <= 1.0

    def test_version_image_presente(self, client):
        """/health doit exposer la version de l'image (SHA du build CI, "dev" en local)."""
        data = client.get("/health").json()
        assert "version_image" in data
        assert isinstance(data["version_image"], str)
        assert len(data["version_image"]) > 0


# =============================================================================
# GET /v1/models — Liste des modèles
# =============================================================================


class TestListeModels:
    """Tests de la route GET /v1/models."""

    def test_statut_200(self, client):
        response = client.get("/v1/models")
        assert response.status_code == 200

    def test_structure_liste(self, client):
        data = client.get("/v1/models").json()
        assert data["object"] == "list"
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

    def test_contenu_modele(self, client):
        """Le premier modèle doit être notre classifier avec ses infos."""
        modele = client.get("/v1/models").json()["data"][0]
        assert modele["id"] == "film-classifier"
        assert modele["object"] == "model"
        for cle in ("version", "type", "runtime", "f1_score"):
            assert cle in modele, f"Clé manquante dans /v1/models : {cle}"

    def test_coherence_avec_health(self, client):
        """La version exposée dans /v1/models doit être la même que /health."""
        health = client.get("/health").json()
        models = client.get("/v1/models").json()["data"][0]
        assert models["version"] == health["version"]
        assert models["type"] == health["type"]


# =============================================================================
# POST /predict — Succès (vrai modèle)
# =============================================================================


class TestPredictSucces:
    """Tests de POST /predict avec des textes valides (vrai modèle TFLite)."""

    def test_statut_200(self, client, texte_comedie):
        response = client.post("/predict", json={"texte": texte_comedie})
        assert response.status_code == 200

    def test_schema_reponse(self, client, texte_comedie):
        """La réponse doit respecter le schéma PredictResponse."""
        data = client.post("/predict", json={"texte": texte_comedie}).json()
        assert isinstance(data["classe"], str)
        assert isinstance(data["probabilite"], float)
        assert isinstance(data["version"], str)
        assert data["type_modele"] == "tflite"

    def test_format_classe(self, client, texte_comedie):
        """La classe doit suivre le format exact '0 : comédie' ou '1 : horreur'."""
        data = client.post("/predict", json={"texte": texte_comedie}).json()
        assert re.fullmatch(r"[01] : (comédie|horreur)", data["classe"])

    def test_texte_comedie(self, client, texte_comedie):
        """Un résumé comique doit renvoyer la classe comédie (string binaire)."""
        data = client.post("/predict", json={"texte": texte_comedie}).json()
        assert data["classe"] in ("0 : comédie", "1 : horreur")  # Le modèle décide, mais les valeurs sont figées
        assert 0.0 <= data["probabilite"] <= 1.0

    def test_texte_horreur(self, client, texte_horreur):
        """Un résumé d'horreur doit renvoyer la classe horreur (string binaire)."""
        data = client.post("/predict", json={"texte": texte_horreur}).json()
        assert data["classe"] in ("0 : comédie", "1 : horreur")
        assert 0.0 <= data["probabilite"] <= 1.0

    def test_version_coherente_avec_health(self, client, texte_comedie):
        """La version renvoyée par /predict doit être celle du /health."""
        health = client.get("/health").json()
        predict = client.post("/predict", json={"texte": texte_comedie}).json()
        assert predict["version"] == health["version"]

    def test_coherence_classe_probabilite(self, client, texte_comedie, texte_horreur):
        """classe = '1 : horreur' si probabilite > 0.5, sinon '0 : comédie' (logique de l'API)."""
        for texte in (texte_comedie, texte_horreur):
            data = client.post("/predict", json={"texte": texte}).json()
            classe_attendue = "1 : horreur" if data["probabilite"] > 0.5 else "0 : comédie"
            assert data["classe"] == classe_attendue


# =============================================================================
# POST /predict — Erreurs de validation (422)
# =============================================================================


class TestPredictValidation:
    """Tests des erreurs 422 : la validation Pydantic rejette la requête avant le modèle."""

    def test_texte_manquant(self, client):
        """Requête sans le champ 'texte' → 422."""
        response = client.post("/predict", json={})
        assert response.status_code == 422

    def test_texte_vide(self, client):
        """Texte vide → 422 (min_length=42)."""
        response = client.post("/predict", json={"texte": ""})
        assert response.status_code == 422

    def test_texte_trop_court(self, client):
        """Texte < 42 caractères → 422."""
        response = client.post("/predict", json={"texte": "This is a short movie text."})
        assert response.status_code == 422

    def test_texte_trop_long(self, client):
        """Texte > 10 000 caractères → 422 (max_length=10000)."""
        texte = "A terrifying horror movie with a very dark atmosphere. " * 200
        assert len(texte) > 10000
        response = client.post("/predict", json={"texte": texte})
        assert response.status_code == 422

    def test_texte_francais(self, client, texte_francais):
        """Texte en français → 422 (l'API n'accepte que l'anglais)."""
        response = client.post("/predict", json={"texte": texte_francais})
        assert response.status_code == 422

    def test_message_erreur_langue(self, client, texte_francais):
        """Le message d'erreur doit mentionner l'exigence d'anglais."""
        response = client.post("/predict", json={"texte": texte_francais})
        detail = str(response.json())
        assert "english" in detail.lower() or "anglais" in detail.lower()

    def test_texte_mauvais_type(self, client):
        """'texte' en int au lieu de str → 422."""
        response = client.post("/predict", json={"texte": 42})
        assert response.status_code == 422

    def test_pas_de_champs_supplementaires_bloquants(self, client, texte_comedie):
        """Vérifie qu'un JSON valide ne renvoie pas 422 (test de non-régression)."""
        response = client.post("/predict", json={"texte": texte_comedie})
        assert response.status_code == 200


# =============================================================================
# POST /predict — Nettoyage de l'entrée (preprocessing.py)
# =============================================================================


class TestNettoyageEntree:
    """Le nettoyage supprime les faux rejets (422/500) sans changer les prédictions."""

    def test_texte_bruite_accepte(self, client, texte_comedie):
        """Retours à la ligne, tabulations, invisibles, HTML, emojis → 200, pas de crash."""
        texte_bruite = "\ufeff<p>" + texte_comedie.replace(" ", "\n", 12) + "</p>\n\t\U0001F480\U0001F600"
        response = client.post("/predict", json={"texte": texte_bruite})
        assert response.status_code == 200

    def test_meme_probabilite_que_texte_propre(self, client, texte_comedie):
        """Non-régression : le bruit neutralisé par le nettoyage ne change PAS la prédiction."""
        texte_bruite = "<p>" + texte_comedie.replace(" ", "\n", 12) + "</p> \U0001F480"
        proba_propre = client.post("/predict", json={"texte": texte_comedie}).json()["probabilite"]
        proba_bruitee = client.post("/predict", json={"texte": texte_bruite}).json()["probabilite"]
        assert proba_bruitee == pytest.approx(proba_propre, abs=1e-9)

    def test_texte_sans_contenu_lisible(self, client):
        """Un texte fait uniquement d'espacements/invisibles → 422 avec un message clair."""
        response = client.post("/predict", json={"texte": " \n\t\u200b\ufeff" * 20})
        assert response.status_code == 422
        assert "lisible" in str(response.json()).lower()

    def test_min_length_appliquee_au_texte_nettoye(self, client):
        """La longueur minimale (42) s'applique au texte NETTOYÉ, pas au texte brut."""
        # 28 caractères lisibles + 100 sauts de ligne : 128 bruts, 28 nets → 422
        texte = "This is a tiny film summary!" + "\n" * 100
        response = client.post("/predict", json={"texte": texte})
        assert response.status_code == 422
        assert "42" in str(response.json())

    def test_francais_bruite_toujours_rejete(self, client, texte_francais):
        """Le nettoyage ne doit pas permettre de contourner la détection de langue."""
        texte_bruite = "<p>" + texte_francais.replace(" ", "\n", 8) + "</p>"
        response = client.post("/predict", json={"texte": texte_bruite})
        assert response.status_code == 422
        detail = str(response.json())
        assert "english" in detail.lower() or "anglais" in detail.lower()


# =============================================================================
# POST /predict — Erreur interne (500, avec mock)
# =============================================================================


class TestPredictErreurs:
    """Test de l'erreur 500 : model_loader.predict lève une exception (mock)."""

    def test_erreur_interne_500(self, client, monkeypatch, texte_comedie):
        """Si le modèle plante, l'API doit renvoyer 500 avec un détail."""

        def faux_predict(text: str) -> float:
            raise RuntimeError("Crash simulé du modèle")

        # On remplace la méthode predict du singleton utilisé par l'API
        monkeypatch.setattr(
            "deeplearning_create_optimize_pushtoprod.api.model_loader.predict",
            faux_predict,
        )

        response = client.post("/predict", json={"texte": texte_comedie})

        assert response.status_code == 500
        assert "detail" in response.json()
        assert "Crash simulé" in response.json()["detail"]
