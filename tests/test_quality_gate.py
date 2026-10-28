"""
Tests de la barrière qualité — quality_gate.py.

Scénarios testés (brief, partie 2, A, 4) :
- le vrai modèle (model/metrics.json) est ACCEPTÉ ;
- un faux modèle (F1 très bas) est REFUSÉ ;
- un jeu de test trop petit est REFUSÉ ;
- fichiers manquants / malformés / clés absentes → REFUS propre.

Exécution :
    uv run pytest tests/test_quality_gate.py
"""

import json
from pathlib import Path

from deeplearning_create_optimize_pushtoprod.quality_gate import METRICS_PATH, verifier_qualite

# =============================================================================
# OUTILS — Fichiers factices
# =============================================================================


def ecrire_metrics(chemin: Path, **valeurs: object) -> None:
    """Écrit un metrics.json factice dans tmp_path avec les valeurs données."""
    contenu = {"f1_score_test": 0.8608, "test_size": 470}
    contenu.update(valeurs)
    chemin.write_text(json.dumps(contenu), encoding="UTF-8")


# =============================================================================
# VRAI MODÈLE — Doit être accepté
# =============================================================================


class TestModeleReel:
    """La barrière doit accepter les métriques réelles du modèle entraîné."""

    def test_modele_reel_accepte(self):
        """Chemins par défaut (config.yaml + model/metrics.json) → accepté."""
        ok, messages = verifier_qualite()
        assert ok is True, f"Le vrai modèle doit passer la barrière : {messages}"
        assert all(message.startswith("✅") for message in messages)

    def test_vrai_f1_au_dessus_du_seuil(self):
        """Vérification chiffrée : le vrai modèle est accepté avec SES métriques.

        Les valeurs attendues sont lues dans model/metrics.json (la même source
        que la barrière) : ce test ne casse plus à chaque réentraînement
        (TODO résolu — l'ancienne valeur 0.8608 était codée en dur).
        """
        ok, messages = verifier_qualite()
        assert ok is True

        with open(METRICS_PATH, encoding="UTF-8") as f:
            attendu = json.load(f)
        f1_attendu = f"{float(attendu['f1_score_test']):.4f}"  # même formatage que la barrière
        n_test_attendu = str(int(attendu["test_size"]))

        # La barrière doit rapporter les métriques RÉELLES du modèle servi
        assert any(f1_attendu in message for message in messages), messages
        assert any(n_test_attendu in message for message in messages), messages


# =============================================================================
# FAUX MODÈLE — Doit être refusé
# =============================================================================


class TestFauxModele:
    """Un faux modèle avec un F1 très bas doit être refusé (exigence du brief)."""

    def test_faux_modele_f1_tres_bas_refuse(self, tmp_path):
        """F1 = 0.42 (inventé) → refusé, même si test_size est correct."""
        metrics = tmp_path / "faux_metrics.json"
        ecrire_metrics(metrics, f1_score_test=0.42)

        ok, messages = verifier_qualite(chemin_metrics=metrics)

        assert ok is False
        assert any("F1" in message and message.startswith("❌") for message in messages)

    def test_jeu_de_test_trop_petit_refuse(self, tmp_path):
        """F1 correct mais test_size = 50 → refusé (jeu de test réduit de manière suspecte)."""
        metrics = tmp_path / "faux_metrics.json"
        ecrire_metrics(metrics, test_size=50)

        ok, messages = verifier_qualite(chemin_metrics=metrics)

        assert ok is False
        assert any("jeu de test" in message and message.startswith("❌") for message in messages)

    def test_faux_modele_double_defaut_refuse(self, tmp_path):
        """F1 bas ET petit jeu de test → refusé, les deux échecs sont signalés."""
        metrics = tmp_path / "faux_metrics.json"
        ecrire_metrics(metrics, f1_score_test=0.42, test_size=12)

        ok, messages = verifier_qualite(chemin_metrics=metrics)

        assert ok is False
        echecs = [message for message in messages if message.startswith("❌")]
        assert len(echecs) == 2


# =============================================================================
# ROBUSTESSE — Fichiers et clés manquantes
# =============================================================================


class TestRobustesse:
    """La barrière doit échouer proprement, sans crash, sur des entrées invalides."""

    def test_metrics_introuvable(self, tmp_path):
        ok, messages = verifier_qualite(chemin_metrics=tmp_path / "inexistant.json")
        assert ok is False
        assert any("introuvable" in message for message in messages)

    def test_config_introuvable(self, tmp_path):
        ok, messages = verifier_qualite(chemin_config=tmp_path / "inexistant.yaml")
        assert ok is False
        assert any("introuvable" in message for message in messages)

    def test_metrics_malforme(self, tmp_path):
        metrics = tmp_path / "corrompu.json"
        metrics.write_text("{ pas du json", encoding="UTF-8")
        ok, messages = verifier_qualite(chemin_metrics=metrics)
        assert ok is False
        assert any("malformé" in message for message in messages)

    def test_cle_manquante_dans_metrics(self, tmp_path):
        """metrics.json sans la clé f1_score_test → refus avec message clair."""
        metrics = tmp_path / "incomplet.json"
        metrics.write_text(json.dumps({"test_size": 470}), encoding="UTF-8")
        ok, messages = verifier_qualite(chemin_metrics=metrics)
        assert ok is False
        assert any("f1_score_test" in message for message in messages)

    def test_cle_manquante_dans_config(self, tmp_path):
        """config.yaml sans la clé test_size_minimum → refus avec message clair."""
        config = tmp_path / "config_incomplet.yaml"
        config.write_text("f1_minimum: 0.83", encoding="UTF-8")
        ok, messages = verifier_qualite(chemin_config=config)
        assert ok is False
        assert any("test_size_minimum" in message for message in messages)


# =============================================================================
# CODE DE SORTIE — main()
# =============================================================================


class TestCodeSortie:
    """Le script CLI doit renvoyer 0 (accepté) ou 1 (refusé) pour la CI."""

    def test_exit_0_vrai_modele(self):
        from deeplearning_create_optimize_pushtoprod.quality_gate import main

        assert main([]) == 0

    def test_exit_1_faux_modele(self, tmp_path):
        from deeplearning_create_optimize_pushtoprod.quality_gate import main

        metrics = tmp_path / "faux_metrics.json"
        ecrire_metrics(metrics, f1_score_test=0.42)
        assert main(["--metrics", str(metrics)]) == 1
