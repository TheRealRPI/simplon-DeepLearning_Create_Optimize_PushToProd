"""
Tests du log JSONL des prédictions (plan monitoring §5.6).

Scénarios :
- un 200 écrit une ligne JSON valide (schéma §5.3) ;
- un 422 produit prediction: null + un motif mappé (langue:fr, trop_court,
  corps_invalide) ;
- l'en-tête X-Monitoring-Source distingue golden_set / production (D8),
  une valeur invalide retombe silencieusement sur production (M10) ;
- NON-FATALITÉ (A2) : un log impossible ne casse pas la requête ;
- PREDICTIONS_LOG_ENABLED=0 → aucun fichier écrit.

Les tests détournent LOG_PATH vers tmp_path (le défaut /data n'existe qu'en
conteneur avec un volume).

Exécution :
    uv run pytest tests/test_predictions_log.py
"""

import json

import pytest

from deeplearning_create_optimize_pushtoprod import predictions_log

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    """Détourne le log JSONL vers un fichier temporaire."""
    chemin = tmp_path / "predictions.jsonl"
    monkeypatch.setattr(predictions_log, "LOG_PATH", chemin)
    monkeypatch.setattr(predictions_log, "ENABLED", True)
    return chemin


def lire_lignes(chemin) -> list[dict]:
    """Lit le JSONL → liste de dicts (une ligne par requête)."""
    contenu = chemin.read_text(encoding="utf-8")
    return [json.loads(ligne) for ligne in contenu.splitlines() if ligne]


# =============================================================================
# 200 — schéma complet d'une ligne
# =============================================================================


class TestLigne200:
    def test_une_ligne_json_valide(self, client, texte_comedie, log_path):
        response = client.post("/predict", json={"texte": texte_comedie})
        assert response.status_code == 200
        assert log_path.exists()

        lignes = lire_lignes(log_path)
        assert len(lignes) == 1
        ligne = lignes[0]

        # Schéma §5.3 : les 12 champs attendus
        for cle in (
            "ts", "request_id", "source", "route", "status", "motif",
            "latency_ms", "model_version", "image_version", "texte",
            "descripteurs", "prediction",
        ):
            assert cle in ligne, f"Champ manquant dans la ligne de log : {cle}"

    def test_valeurs_coheres(self, client, texte_comedie, log_path):
        """Contenu de la ligne : attribution, descripteurs, prédiction."""
        client.post("/predict", json={"texte": texte_comedie})
        ligne = lire_lignes(log_path)[0]

        assert ligne["source"] == "production"
        assert ligne["route"] == "/predict"
        assert ligne["status"] == 200
        assert ligne["motif"] is None
        assert ligne["model_version"] == "1.1.0"        # metrics.json servi
        assert isinstance(ligne["image_version"], str) and ligne["image_version"]
        assert ligne["request_id"]                      # traçable
        assert isinstance(ligne["latency_ms"], float) and ligne["latency_ms"] >= 0

        # Le texte logué est le texte NETTOYÉ (vu par le modèle)
        assert isinstance(ligne["texte"], str) and ligne["texte"]

        pred = ligne["prediction"]
        assert pred["classe"] in (0, 1)                 # int, pas "1 : horreur"
        assert 0.0 <= pred["proba"] <= 1.0
        assert pred["seuil"] == 0.5

        desc = ligne["descripteurs"]
        assert desc["langue"] == "en"                   # validé par l'API
        assert desc["nb_mots"] > 0
        assert desc["longueur"] >= 42                    # min_length post-nettoyage
        assert 0.0 <= desc["oov_rate"] <= 1.0

    def test_deux_requetes_deux_lignes(self, client, texte_comedie, log_path):
        client.post("/predict", json={"texte": texte_comedie})
        client.post("/predict", json={"texte": texte_comedie})
        assert len(lire_lignes(log_path)) == 2


# =============================================================================
# 422 — rejets de validation logués avec leur motif (M6)
# =============================================================================


class TestLigne422:
    def test_francais(self, client, texte_francais, log_path):
        """Rejet de langue → prediction null + motif langue:fr (A3)."""
        response = client.post("/predict", json={"texte": texte_francais})
        assert response.status_code == 422

        ligne = lire_lignes(log_path)[0]
        assert ligne["status"] == 422
        assert ligne["prediction"] is None
        assert ligne["descripteurs"] is None
        assert ligne["motif"] == "langue:fr"

    def test_trop_court(self, client, log_path):
        client.post("/predict", json={"texte": "This is a short movie text."})
        ligne = lire_lignes(log_path)[0]
        assert ligne["status"] == 422
        assert ligne["motif"] == "trop_court"

    def test_corps_invalide(self, client, log_path):
        """'texte' de mauvais type → corps_invalide (pas de texte exploitable)."""
        client.post("/predict", json={"texte": 42})
        ligne = lire_lignes(log_path)[0]
        assert ligne["status"] == 422
        assert ligne["motif"] == "corps_invalide"
        assert ligne["texte"] is None

    def test_vide_apres_nettoyage(self, client, log_path):
        """Texte réduit à rien par le nettoyage → motif vide_apres_nettoyage."""
        client.post("/predict", json={"texte": " \n\t\u200b\ufeff" * 20})
        ligne = lire_lignes(log_path)[0]
        assert ligne["motif"] == "vide_apres_nettoyage"


# =============================================================================
# X-Monitoring-Source (D8) — séparer trafic réel et rejeu
# =============================================================================


class TestSource:
    def test_golden_set(self, client, texte_comedie, log_path):
        """Le rejeu du golden set doit être marqué : sinon la dérive est faussée."""
        client.post(
            "/predict",
            json={"texte": texte_comedie},
            headers={"X-Monitoring-Source": "golden_set"},
        )
        assert lire_lignes(log_path)[0]["source"] == "golden_set"

    def test_valeur_invalide_silencieusement_production(self, client, texte_comedie, log_path):
        """M10 : valeur inconnue → retour au défaut production, jamais de 400."""
        response = client.post(
            "/predict",
            json={"texte": texte_comedie},
            headers={"X-Monitoring-Source": "n_importe_quoi"},
        )
        assert response.status_code == 200
        assert lire_lignes(log_path)[0]["source"] == "production"


# =============================================================================
# NON-FATALITÉ (A2) et désactivation
# =============================================================================


class TestNonFatalite:
    def test_log_impossible_requete_ok(self, client, texte_comedie, tmp_path, monkeypatch):
        """Un échec d'écriture (mkdir impossible) ne casse PAS la réponse.

        LOG_PATH pointe SOUS un fichier existant : mkdir lève, log_prediction
        avale, la requête renvoie quand même 200.
        """
        bloqueur = tmp_path / "pas_un_dossier"
        bloqueur.write_text("je suis un fichier", encoding="utf-8")
        monkeypatch.setattr(
            predictions_log, "LOG_PATH", bloqueur / "predictions.jsonl"
        )

        response = client.post("/predict", json={"texte": texte_comedie})
        assert response.status_code == 200
        assert "probabilite" in response.json()

    def test_desactive_aucun_fichier(self, client, texte_comedie, tmp_path, monkeypatch):
        """PREDICTIONS_LOG_ENABLED=0 → la requête passe, RIEN n'est écrit."""
        chemin = tmp_path / "desactive.jsonl"
        monkeypatch.setattr(predictions_log, "LOG_PATH", chemin)
        monkeypatch.setattr(predictions_log, "ENABLED", False)

        response = client.post("/predict", json={"texte": texte_comedie})
        assert response.status_code == 200
        assert not chemin.exists()


# =============================================================================
# CONCURRENCE — les BackgroundTasks loggent en parallèle (threadpool)
# =============================================================================


class TestConcurrence:
    def test_ecritures_paralleles_sans_corruption(self, monkeypatch, tmp_path):
        """20 threads × 20 lignes de ~12 Ko : sans verrou, les écritures
        multi-chunks (lignes > buffer 8 Ko) s'entrelacent — bug mesuré en P3
        en démo compose (114 lignes cassées). Avec le verrou : 400 lignes,
        toutes valides.
        """
        import threading

        chemin = tmp_path / "concurrent.jsonl"
        monkeypatch.setattr(predictions_log, "LOG_PATH", chemin)
        monkeypatch.setattr(predictions_log, "ENABLED", True)

        def ecrire(tid: int) -> None:
            for i in range(20):
                predictions_log.log_prediction(
                    source="production",
                    route="/predict",
                    status=200,
                    texte=f"t{tid}-{i}-" + "x" * 12_000,  # > buffer 8 Ko → multi-chunks
                    prediction={"proba": 0.5, "classe": 1, "seuil": 0.5},
                )

        threads = [threading.Thread(target=ecrire, args=(t,)) for t in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lignes = chemin.read_text(encoding="utf-8").splitlines()
        assert len(lignes) == 400
        for ligne in lignes:  # aucune ligne corrompue
            assert json.loads(ligne)["status"] == 200
