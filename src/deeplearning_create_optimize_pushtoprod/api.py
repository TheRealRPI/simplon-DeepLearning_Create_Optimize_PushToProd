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
from time import perf_counter
from typing import Annotated, Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from langdetect import DetectorFactory, LangDetectException, detect
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .descriptors import langue, longueur, nb_mots, oov_rate
from .model_loader import model_loader
from .predictions_log import log_prediction
from .preprocessing import nettoyer_texte

# =============================================================================
# DÉTECTION DE LANGUE — CONFIG
# =============================================================================
# langdetect utilise de l'aléatoire : fixer le seed le rend déterministe
# (même texte => même langue, indispensable pour une API)
DetectorFactory.seed = 42

# =============================================================================
# MONITORING — constantes calculées UNE FOIS au chargement (jamais par requête)
# =============================================================================

# Version de l'image (SHA du build CI, "dev" en local) — sans elle, une chute
# de F1 n'est rattachable à aucun release → inactionnable.
_IMAGE_VERSION = getenv("IMAGE_VERSION", "dev")

# oov_rate (§5.1 du plan monitoring) : analyzer et vocabulaire du vectoriseur
# RÉELLEMENT SERVI — build_analyzer() garantit lowercase / token_pattern /
# ngram_range(1,2) identiques à l'entraînement, jamais une tokenisation maison.
_VOCABULAIRE = set(model_loader.vectoriseur.vocabulary_)  # 9 005 termes
_ANALYZER = model_loader.vectoriseur.build_analyzer()

# Sources acceptées dans X-Monitoring-Source (D8 : le schéma public /predict
# ne change pas — le mode golden set passe par un simple en-tête).
_SOURCES_VALIDES = {"production", "golden_set"}

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

    Le texte est d'abord NETTOYÉ (sauts de ligne, caractères invisibles, HTML,
    typographie → cf. preprocessing.py) : les contraintes ci-dessous
    s'appliquent donc au texte nettoyé, comme à l'entraînement.
    """

    # Défini le champ 'texte' avec validation
    texte: str = Field(
        ...,  # ... = Ellipsis en Python = "ce champ est obligatoire"
        min_length=42,
        max_length=10000,
        description="Résumé du film à classifier (en anglais) — nettoyé automatiquement avant l'inférence",
    )

    # Nettoyage AVANT toute validation (mode="before") : min_length, max_length
    # et la détection de langue s'appliquent au texte RÉEL, pas au bruit
    @field_validator("texte", mode="before")
    @classmethod
    def nettoyer(cls, v: object) -> object:
        """Nettoie le texte en entrée (espacements, invisibles, HTML, typographie)."""
        texte_propre = nettoyer_texte(v)
        # Un texte réduit à rien par le nettoyage (espaces, \n, invisibles...)
        # est rejeté avec un message clair plutôt qu'avec l'erreur obscure de langdetect
        if isinstance(texte_propre, str) and not texte_propre:
            raise ValueError("Le texte ne contient aucun contenu lisible à classifier (vide après nettoyage).")
        return texte_propre

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
# MONITORING — handler 422 : loguer le rejet, puis relayer la 422 STANDARD
# =============================================================================
# langdetect, min_length et max_length échouent tous dans des field_validator
# (ou dans Pydantic) → ils transitent par RequestValidationError : ce handler
# voit TOUS les rejets de validation. Le corps de la réponse est celui du
# handler PAR DÉFAUT de FastAPI, à l'identique (tests existants inchangés).
# Les 422 n'atteignent jamais le modèle : sans ce log, le trafic paraît
# stable alors qu'il s'effondre (§5.3 du plan).


@app.exception_handler(RequestValidationError)
async def log_422_puis_relais(request: Request, exc: RequestValidationError):
    """Logue le rejet (source, motif, texte si extractible) — jamais bloquant."""
    texte, motif = _extraire_422(exc)
    log_prediction(
        source=_source_valide(request.headers.get("x-monitoring-source")),
        route="/predict",
        status=422,
        motif=motif,
        texte=texte,
    )
    # Relais strict de la 422 standard (aucune modification du corps)
    return await request_validation_exception_handler(request, exc)

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
# MONITORING — helpers de log (tout est non bloquant, jamais levé)
# =============================================================================


def _source_valide(valeur: str | None) -> str:
    """X-Monitoring-Source → "production" (défaut) ou "golden_set".

    Une valeur invalide est ignorée silencieusement : jamais de 400 sur un
    en-tête de télémétrie (M10) — le rejeu golden set ne pollue pas les
    stats de dérive, et le trafic normal n'est jamais écarté.
    """
    return valeur if valeur in _SOURCES_VALIDES else "production"


def _descripteurs(texte: str) -> dict[str, object]:
    """Descripteurs du texte DÉJÀ NETTOYÉ (ils décrivent ce que voit le vectoriseur).

    Appelé en tâche de fond : le coût (langdetect, oov_rate) ne touche
    pas la latence de la réponse.
    """
    return {
        "longueur": longueur(texte),
        "nb_mots": nb_mots(texte),
        "langue": langue(texte),
        "oov_rate": round(oov_rate(texte, _ANALYZER, _VOCABULAIRE), 4),
    }


def _log_200(texte: str, proba: float, cat: int, version: str, source: str, latence_ms: float) -> None:
    """Ligne JSONL d'une prédiction 200 — en tâche de fond, APRÈS la réponse."""
    log_prediction(
        source=source,
        route="/predict",
        status=200,
        texte=texte,
        prediction={"proba": proba, "classe": cat, "seuil": 0.5},
        descripteurs=_descripteurs(texte),
        latency_ms=round(latence_ms, 2),
        model_version=version,
    )


def _motif_422(exc: RequestValidationError) -> str:
    """Mappe les erreurs Pydantic vers un motif lisible (M6), avec fallback générique."""
    for erreur in exc.errors():
        type_erreur = erreur.get("type", "")
        message = str(erreur.get("msg", ""))
        if type_erreur == "string_too_short":
            return "trop_court"
        if type_erreur == "string_too_long":
            return "trop_long"
        # Messages des validators maison (type "value_error")
        if "Detected language" in message:
            # "...Text must be in english (Detected language : fr)."
            code = message.split("Detected language :")[-1].strip().rstrip(").").strip()
            return f"langue:{code or 'inconnue'}"
        if "Impossible de détecter la langue" in message:
            return "langue:indetectable"
        if "ne contient aucun contenu lisible" in message:
            return "vide_apres_nettoyage"
    return "validation_invalide"


def _extraire_422(exc: RequestValidationError) -> tuple[str | None, str]:
    """Extrait (texte, motif) d'une erreur de validation.

    - corps JSON avec un champ "texte" str → texte + motif mappé ;
    - sinon (JSON invalide, champ absent, type inattendu) → (None, "corps_invalide").
    """
    corps = exc.body
    if isinstance(corps, dict) and isinstance(corps.get("texte"), str):
        return corps["texte"], _motif_422(exc)
    return None, "corps_invalide"


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
    background_tasks: BackgroundTasks,
    x_monitoring_source: Annotated[str | None, Header(alias="X-Monitoring-Source")] = None,
) -> PredictResponse:
    """
    Reçoit un résumé de film et prédit sa catégorie (horreur ou comédie).

    - **texte** : le résumé du film (obligatoire, 42 à 10 000 caractères après nettoyage, anglais uniquement)

    Retourne :
    - **classe** : 0 (comédie) ou 1 (horreur)
    - **probabilite** : probabilité de la classe prédite
    - **version** : version du modèle utilisé

    Monitoring (D8) : l'en-tête facultatif X-Monitoring-Source ("golden_set")
    permet au rejeu du golden set de ne pas polluer le trafic "production"
    dans les logs JSONL. Le schéma public reste inchangé.
    """

    # Latence mesurée CÔTÉ HANDLER (t0 → calcul) : jamais en tâche de fond,
    # sinon on chronomètre après la réponse (M5).
    t0 = perf_counter()
    source = _source_valide(x_monitoring_source)

    try:
        probabilite = model_loader.predict(request.texte)
        cat = 1 if probabilite > 0.5 else 0
        version = model_loader.get_model_info()["version"]

        # Log NON bloquant : la ligne part en tâche de fond, APRÈS la réponse
        # (le coût des descripteurs ne touche pas la latence).
        background_tasks.add_task(
            _log_200,
            texte=request.texte,
            proba=probabilite,
            cat=cat,
            version=version,
            source=source,
            latence_ms=(perf_counter() - t0) * 1000,
        )

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
        # Erreur imprévue : log non bloquant (motif "exception"), puis 500
        log_prediction(
            source=source,
            route="/predict",
            status=500,
            motif="exception",
            texte=request.texte,
            latency_ms=round((perf_counter() - t0) * 1000, 2),
            model_version=model_loader.get_model_info()["version"],
        )
        # Détail renvoyé au client dans le JSON {"detail": ...}
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne de l'application. Erreur : {e}",
        ) from e


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
