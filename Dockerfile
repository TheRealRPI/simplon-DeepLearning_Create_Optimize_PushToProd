# =============================================================================
# DOCKERFILE — API de classification horreur vs comédie (modèle TFLite)
# =============================================================================
# Image volontairement SANS TensorFlow : l'inférence passe par LiteRT.
# Entraînement (lourd, GPU) = local ; service (léger, CPU) = conteneur.
#
# Contenu : code de l'API (src/) + artefacts modèle (model/) uniquement.
# Les tests et la barrière qualité ne sont PAS dans l'image : ils tournent
# en CI, sur des jobs dédiés, indépendamment de ce build.
#
# Build : docker build -t film-api .
# Run   : docker run --rm -p 8000:8000 film-api
# =============================================================================

FROM python:3.13-slim

# Python sans buffers ni .pyc (logs immédiats, image propre)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# --- MÉTADONNÉES OCI (visibles via docker inspect) ------------------------------
# version          = version du projet (pyproject.toml)
# model-version    = version du modèle embarqué (model/metrics.json)
LABEL org.opencontainers.image.title="film-api" \
      org.opencontainers.image.description="API de classification de résumés de films (horreur vs comédie) — modèle TFLite/LiteRT" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.authors="TheRealRPI"

# --- 1) DÉPENDANCES (copie AVANT le code = cache des layers) -------------------
# Tant que requirements.txt ne change pas, pip n'est pas re-exécuté.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- 2) VERSION DE L'IMAGE ---------------------------------------------------------
# SHA du commit, injecté par la CI : docker build --build-arg IMAGE_VERSION=<sha>.
# Lu par /health (os.getenv) pour exposer la version de l'image déployée.
# Placé APRÈS le pip install : un SHA nouveau n'invalide pas le cache des deps.
ARG IMAGE_VERSION=dev
ENV IMAGE_VERSION=${IMAGE_VERSION}

# --- 3) CODE + ARTEFACTS MODÈLE -------------------------------------------------
# .dockerignore filtre déjà le superflu : model/ ne livrera que
# model.tflite, vectoriseur.joblib et metrics.json.
COPY src/ ./src/
COPY model/ ./model/

# Le package vit dans src/ (layout src), pas d'installation nécessaire
ENV PYTHONPATH=/app/src

# --- 4) DURCISSEMENT : utilisateur non-root ---------------------------------------
RUN useradd --create-home apiuser \
    && chown -R apiuser:apiuser /app
USER apiuser

# --- 5) RÉSEAU + SANTÉ -------------------------------------------------------------
# python:slim n'a ni curl ni wget : le healthcheck passe par urllib.
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "deeplearning_create_optimize_pushtoprod.api:app", "--host", "0.0.0.0", "--port", "8000"]
