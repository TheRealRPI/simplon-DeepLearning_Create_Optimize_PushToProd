"""
API FastAPI — Classification de résumés de films (horreur vs comédie).

Routes :
- GET  /health  : Vérifie que l'API est vivante + infos modèle
- POST /predict : Reçoit un texte (en anglais), renvoie la classe prédite

Lancement :
    uvicorn deeplearning_create_optimize_pushtoprod.api:app --reload

Auteur : TheRealRPI
Date   : 26/10/2026
"""
# =============================================================================
# IMPORTS
# =============================================================================

# TODO: Importer ton ModelLoader
# Indice : from .model_loader import model_loader (ou le chemin relatif)
from contextlib import asynccontextmanager
from os import getenv
from typing import Any

from fastapi import FastAPI, HTTPException
from langdetect import DetectorFactory, LangDetectException, detect
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .model_loader import model_loader

# =============================================================================
# DÉTECTION DE LANGUE — CONFIG
# =============================================================================
# langdetect utilise de l'aléatoire : fixer le seed le rend déterministe
# (même texte => même langue, indispensable pour une API)
DetectorFactory.seed = 42

# =============================================================================
# SCHÉMA PYDANTIC — Validation des entrées
# =============================================================================


class PredictRequest(BaseModel):
    """
    Schéma de validation pour la requête POST /predict.

    Le texte doit :
    - être une chaîne de caractères (str)
    - avoir une longueur minimale (évite les textes vides ou trop courts)
    - être en anglais
    """

    # Défini le champ 'texte' avec validation
    texte: str = Field(
        ...,  # ... = Ellipsis en Python = "ce champ est obligatoire"
        min_length=42,
        max_length=10000,
        description="Résumé du film à classifier (en anglais)",
    )

    @field_validator("texte")
    @classmethod
    # cls = classe (ici PredictRequest)
    def verifier_anglais(cls, v: str) -> str:
        """Rejette le texte s'il n'est pas détecté comme anglais."""
        try:
            langue = detect(v)
        except LangDetectException:
            raise ValueError("Impossible de détecter la langue du texte. L'API n'accepte que l'anglais.")
        if langue != "en":
            raise ValueError(f"Text must be in english (Detected language : {langue}).")
        return v

    # Ajouter un exemple pour la doc Swagger (optionnel mais cool)
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "texte": """Mr. and Mrs. Bunny are devastated when their vegetable garden is wiped out, and everyone
                 wants to know who the thief is. Peepoodo, the cheerful pink hamster, turns detective. Spotting white
                 fur at the scene, he suspects his friend Evelyn, who indignantly replies that she’s no vegan. 
                The investigation takes an awkward turn when Mr. Bunny reveals a very private, very unconventional 
                secret involving his vegetables. The case ends in a messy, gross-out finale that leaves Peepoodo drenched."""
            }
        }
    )


class PredictResponse(BaseModel):
    """
    Schéma de réponse pour POST /predict.
    """

    # Définir les champs de réponse et leur type
    classe: str
    probabilite: float
    version: str
    type_modele: str = "tflite"


# =============================================================================
# LIFESPAN — Chargement du modèle au démarrage
# =============================================================================


# Gestionnaire de cycle de vie (lifespan)
#   fonction async avec @asynccontextmanager
#   Elle reçoit 'app' et fait un 'yield'
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestionnaire du cycle de vie de l'application.

    Au démarrage : charge le modèle (une seule fois).
    À l'arrêt : libère les ressources (optionnel).
    """

    # --- AU DÉMARRAGE ---
    print("🚀 Démarrage de l'API...")
    # Le modèle est déjà chargé via l'import de model_loader
    # Tu peux ajouter des vérifications ici si besoin
    print("✅ Modèle prêt !")

    yield  # L'application démarre ici

    # --- À L'ARRÊT ---
    print("🛑 Arrêt de l'API...")


# =============================================================================
# CRÉATION DE L'APPLICATION FASTAPI
# =============================================================================
app = FastAPI(
    title="Comédie ou Horreur ?", description="API de classification de résumés (horreur vs comédie)", lifespan=lifespan
)

# =============================================================================
# ROUTE GET /health — Vérification de santé
# =============================================================================


@app.get("/health")
async def health() -> dict[str, Any]:
    """
    Vérifie que l'API est vivante et affiche les infos du modèle.

    Retourne :
    - status: "ok"
    - version_image: SHA du commit de build (injecté par la CI, "dev" en local)
    - infos du modèle (version, type, runtime, F1)
    """

    # Récupére les infos du modèle via model_loader
    model_info = model_loader.get_model_info()

    return {
        "status": "ok",
        "version_image": getenv("IMAGE_VERSION", "dev"),
        **model_info,
    }


# =============================================================================
# ROUTE POST /predict — Prédiction
# =============================================================================


@app.post(
    "/predict",
    response_model=PredictResponse,
    summary="Prédire si un film est une comédie ou un tord-boyaux",
    description="Reçoit un résumé et renvoie horreur/comédie",
)
async def predict(
    request: PredictRequest,
) -> PredictResponse:
    """
    Reçoit un résumé de film et prédit sa catégorie (horreur ou comédie).

    - **texte** : le résumé du film (obligatoire, 42 à 10 000 caractères, anglais uniquement)

    Retourne :
    - **classe** : 0 (comédie) ou 1 (horreur)
    - **probabilite** : probabilité de la classe prédite
    - **version** : version du modèle utilisé
    """

    try:
        probabilite = model_loader.predict(request.texte)
        cat = 1 if probabilite > 0.5 else 0
        version = model_loader.get_model_info()["version"]

        return PredictResponse(
            classe=f"{cat} : {'comédie' if cat == 0 else 'horreur'}",
            probabilite=probabilite,
            version=version,
        )

    except HTTPException:
        # Une HTTPException explicite (4xx/5xx) ne doit jamais être avalée
        # par le catch-all ci-dessous — on la relaie telle quelle
        raise

    except Exception as e:
        # Erreur imprévue : détail renvoyé au client dans le JSON {"detail": ...}
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne de l'application. Erreur : {e}",
        )


# =============================================================================
# ROUTE GET / — Page d'accueil (optionnel mais sympa)
# =============================================================================


@app.get("/")
async def root() -> dict[str, str]:
    """
    Page d'accueil avec liens vers la doc.
    """
    return {
        "message": "Bienvenue sur l'API",
        "doc": "/docs",
        "health": "/health",
    }


# =============================================================================
# ROUTE GET /v1/models
# =============================================================================
@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    """
    Liste les modèles disponibles (standard API ML).
    Utilisé par certains outils de monitoring/health check.
    """
    model_info = model_loader.get_model_info()
    return {
        "object": "list",
        "data": [
            {
                "id": "film-classifier",
                "object": "model",
                "version": model_info["version"],
                "type": model_info["type"],
                "runtime": model_info["runtime"],
                "f1_score": model_info.get("f1_score"),
            }
        ],
    }


@app.get("/hello")
def hello():
    return {"message": "Hello depuis la version déployée sur Azure"}


# =============================================================================
# POINT D'ENTRÉE — Lancement avec uvicorn
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    # Lancer le serveur
    #   uvicorn.run(app, host="0.0.0.0", port=8000)
    #   host="0.0.0.0" = accessible depuis l'extérieur (important pour Docker)
    #   port=8000 = port par défaut (sera exposé dans Docker)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )
