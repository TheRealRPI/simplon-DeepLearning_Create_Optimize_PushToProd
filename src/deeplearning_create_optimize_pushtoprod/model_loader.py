"""
ModelLoader — Charge le modèle TFLite (LiteRT) + vectoriseur + métriques.
Fournit une interface simple pour faire des prédictions.

Auteur : TheRealRPI
Date   : 26/10/2026
"""

# =============================================================================
# IMPORTS
# =============================================================================

import json  # Pour lire metrics.json
from pathlib import Path  # Pour gérer les chemins de fichiers
from typing import Any  # Pour les type hints

import joblib  # Pour charger le vectoriseur
from ai_edge_litert.interpreter import Interpreter  # Pour charger le modèle TFLite

# =============================================================================
# CHEMINS VERS LES FICHIERS
# =============================================================================

# Racine du projet : ce fichier est dans src/<pkg>/, on remonte de 3 niveaux
PROJECT_ROOT = Path(__file__).parent.parent.parent
MODEL_DIR = PROJECT_ROOT / "model"
MODEL_PATH = MODEL_DIR / "model.tflite"
VECTORIZER_PATH = MODEL_DIR / "vectoriseur.joblib"
METRICS_PATH = MODEL_DIR / "metrics.json"


class ModelLoader:
    """
    Classe qui encapsule le chargement et l'inférence du modèle TFLite.

    Le modèle est chargé UNE SEULE FOIS à l'instanciation (dans __init__),
    puis réutilisé pour toutes les prédictions via la méthode predict().
    """

    def __init__(self) -> None:
        """
        Charge tous les artefacts au démarrage :
        - Interpréteur LiteRT (pour lire le modèle .tflite)
        - Vectoriseur TF-IDF (pour transformer les textes)
        - Métriques (pour la version et les infos)
        """

        print("🔄 Chargement du modèle TFLite...")

        # -------------------------------------------------------------------------
        # 1. CRÉER L'INTERPRÉTEUR LiteRT
        # -------------------------------------------------------------------------

        # Créer l'interpréteur LiteRT
        self.interpreter = Interpreter(model_path=str(MODEL_PATH))

        # Allouer les tenseurs (préparer la mémoire interne)
        self.interpreter.allocate_tensors()

        # Détails d'entrée/sortie : méthodes qui retournent une liste de dicts → premier tenseur
        self.input_details = self.interpreter.get_input_details()[0]
        self.output_details = self.interpreter.get_output_details()[0]

        # DEBUG: Afficher les infos pour vérifier (à retirer après)
        print(f"   📥 Input shape : {self.input_details['shape']}")
        print(f"   📥 Input dtype : {self.input_details['dtype']}")
        print(f"   📤 Output shape: {self.output_details['shape']}")

        # -------------------------------------------------------------------------
        # 2. CHARGER LE VECTORISEUR
        # -------------------------------------------------------------------------
        print("🔄 Chargement du vectoriseur TF-IDF...")
        self.vectoriseur = joblib.load(VECTORIZER_PATH)

        # -------------------------------------------------------------------------
        # 3. CHARGER LES MÉTRIQUES
        # -------------------------------------------------------------------------
        print("🔄 Chargement des métriques...")
        with open(METRICS_PATH, encoding="UTF-8") as f:
            self.metrics = json.load(f)

        print("✅ Modèle chargé avec succès !")
        print(f"   Version : {self.metrics['model_version']}")

    # =========================================================================
    # MÉTHODE get_model_info() — Pour le endpoint /health
    # =========================================================================

    def get_model_info(self) -> dict[str, Any]:
        """
        Retourne les informations du modèle pour l'endpoint /health.

        Returns:
            dict: Infos sur le modèle (version, type, runtime, F1)
        """

        return {
            "version": self.metrics["model_version"],
            "type": "tflite",
            "runtime": "liteRT",
            "f1_score": self.metrics["f1_score_test"],
            "quantification": self.metrics.get("quantification", {}).get("format"),
        }

    # =========================================================================
    # MÉTHODE predict() — Le cœur de l'inférence
    # =========================================================================

    def predict(self, text: str) -> float:
        """
        Prend un texte brut et renvoie la probabilité d'appartenir à la classe 1 (horreur).

        Flux :
        1. Vectorisation (texte → nombres)
        2. Conversion sparse → dense
        3. Adaptation forme et type
        4. Envoi au modèle (set_tensor)
        5. Inférence (invoke)
        6. Récupération du résultat (get_tensor)

        Args:
            text: Le résumé du film à classifier

        Returns:
            float: Probabilité entre 0 et 1 (1 = horreur, 0 = comédie)
        """

        # -------------------------------------------------------------------------
        # ÉTAPE 1 : Vectorisation
        # -------------------------------------------------------------------------

        # Transformer le texte avec le vectoriseur
        # ⚠️ IMPORTANT : transform() attend une LISTE, pas un string !
        #                Passer [text] et non text
        X_sparse = self.vectoriseur.transform([text])

        # -------------------------------------------------------------------------
        # ÉTAPE 2 : Conversion sparse → dense
        # -------------------------------------------------------------------------

        # Convertir la matrice sparse en array dense (numpy)
        # Indice : méthode .toarray() sur l'objet sparse
        # ⚠️ Le modèle TFLite N'ACCEPTE PAS les matrices sparse !
        X_dense = X_sparse.toarray()

        # -------------------------------------------------------------------------
        # ÉTAPE 3 : Adaptation de la forme (shape)
        # -------------------------------------------------------------------------

        # Récupérer la forme attendue par le modèle
        expected_shape = self.input_details["shape"]
        # Exemple : [1, 9005] ou [1, 10042]

        # Adapter la forme si nécessaire
        if X_dense.shape != tuple(expected_shape):
            X_dense = X_dense.reshape(1, -1)

        # -------------------------------------------------------------------------
        # ÉTAPE 4 : Adaptation du type (dtype)
        # -------------------------------------------------------------------------

        # Récupérer le dtype attendu
        expected_dtype = self.input_details["dtype"]
        # Souvent : np.float32 (ou np.int8 si quantifié)

        # Convertir au bon type
        X_dense = X_dense.astype(expected_dtype)

        # -------------------------------------------------------------------------
        # ÉTAPE 5 : Envoi au modèle (set_tensor)
        # -------------------------------------------------------------------------

        # Récupérer l'index d'entrée
        input_index = self.input_details["index"]

        # Envoyer les données à l'interpréteur
        self.interpreter.set_tensor(input_index, X_dense)

        # -------------------------------------------------------------------------
        # ÉTAPE 6 : Inférence (invoke)
        # -------------------------------------------------------------------------
        self.interpreter.invoke()

        # -------------------------------------------------------------------------
        # ÉTAPE 7 : Récupération du résultat (get_tensor)
        # -------------------------------------------------------------------------

        # Récupérer l'index de sortie
        output_index = self.output_details["index"]

        # Récupérer le résultat
        output = self.interpreter.get_tensor(output_index)

        # -------------------------------------------------------------------------
        # ÉTAPE 8 : Extraction de la probabilité
        # -------------------------------------------------------------------------

        # output est un array de forme (1, 1) → on extrait le float
        probability = float(output[0][0])

        return probability


# =============================================================================
# INSTANCE GLOBALE (Singleton)
# =============================================================================
# Cette instance est créée UNE SEULE FOIS au chargement du module
# Toutes les requêtes utiliseront cette même instance (pas de rechargement)
model_loader = ModelLoader()

if __name__ == "__main__":
    # Tester le chargement et une prédiction

    # Test 1 : Afficher les infos
    print("\n" + "=" * 50)
    print("TEST ModelLoader")
    print("=" * 50)
    print(model_loader.get_model_info())

    # Test 2 : Faire une prédiction
    texte_test = "Seven year-old Albert is the son of a Las Vegas circus performer. When she is killed in a car wreck, Albert is sent to live with his mother's foster sister, Harriet Franklin, a no-nonsense businesswoman struggling in New Jersey. Albert hates it with the dour Harriet, but takes refuge in the company of Bogus, a flamboyant, gentle, loving, and altogether imaginary Frenchman. With Bogus's help, Albert can perhaps come to terms with his mother's death, and Harriet with her own loss of childhood innocence."
    proba = model_loader.predict(texte_test)
    classe = "Horreur" if proba > 0.5 else "Comédie"

    print(f"\nTexte : {texte_test[:100]}...")
    print(f"Probabilité : {proba:.4f}")
    print(f"Classe prédite : {classe}")
