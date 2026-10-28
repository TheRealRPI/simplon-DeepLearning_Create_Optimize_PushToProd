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
#
# -----------------------------------------------------------------------------
# SÉCURITÉ — pourquoi deux étages
# -----------------------------------------------------------------------------
# Les CVE restantes après le passage à bookworm ne venaient PAS de l'OS ni des
# dépendances applicatives, mais de l'outillage de build embarqué dans l'image :
#
#   pypi/urllib3    2.7.0   → vendorisé par pip (requests interne)
#   pypi/msgpack    1.1.2   → vendorisé par pip (cache / CacheControl)
#   pypi/setuptools 70.3.0  → livré avec l'image python:3.13-slim
#
# Aucun paquet applicatif (ai-edge-litert, fastapi, joblib, langdetect,
# pydantic, scikit-learn, uvicorn) ne dépend de msgpack ou d'urllib3 : ces
# copies sont 100 % du tooling de build. Or `pip install --upgrade pip` ne
# suffit pas (pip 26.x vendorise encore urllib3 2.7.0, la version CVE).
#
# D'où la stratégie : construire le venv dans un étage dédié, puis n'emporter
# en production QUE le venv applicatif, après en avoir retiré pip, setuptools
# et wheel — et en supprimant les copies livrées par l'image de base.
# Résultat : la surface CVE pip/setuptools disparaît de l'image finale.
# =============================================================================

# --- ÉTAGE 1 : BUILDER — installation des dépendances ------------------------
# Debian 13 (trixie) plutôt que bookworm : les 2 seules CVE CRITICAL de
# l'image bookworm (libsqlite3 CVE-2025-7458, zlib1g CVE-2023-45853) ne sont
# jamais corrigées en oldstable. Mesuré au scan (Trivy, même base de données) :
#   bookworm : 242 CVE dont 2 critiques   →   trixie : 164 CVE dont 0 critique
FROM python:3.13-slim-trixie AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# venv isolé : c'est le seul artefact transmis à l'étage runtime
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copie AVANT le code = cache des layers : tant que requirements.txt ne change
# pas, pip n'est pas ré-exécuté.
COPY requirements.txt .

# 1) tooling de build à jour (pip/setuptools récents pendant l'installation)
# 2) dépendances applicatives
# 3) tooling retiré du venv : il ne doit jamais atteindre la prod
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt \
    && pip uninstall -y pip setuptools wheel

# --- ÉTAGE 2 : RUNTIME — image finale minimale -------------------------------
# Même base que le builder : le venv copié dépend de l'interpréteur /usr/local.
FROM python:3.13-slim-trixie AS runtime

# Python sans buffers ni .pyc (logs immédiats, image propre)
# PYTHONNOUSERSITE : aucun site-packages utilisateur parasite ($HOME/.local)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONNOUSERSITE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# --- MÉTADONNÉES OCI (visibles via docker inspect) ------------------------------
# version          = version du projet (pyproject.toml)
# model-version    = version du modèle embarqué (model/metrics.json)
LABEL org.opencontainers.image.title="film-api" \
      org.opencontainers.image.description="API de classification de résumés de films (horreur vs comédie) — modèle TFLite/LiteRT" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.authors="TheRealRPI"

# --- 1) DÉPENDANCES : venv du builder, sans pip/setuptools/wheel -------------
COPY --from=builder /opt/venv /opt/venv

# Ceinture et bretelles : l'image python:3.13-slim embarque son propre pip,
# setuptools et ensurepip dans /usr/local. Inutiles au runtime, ce sont eux
# qui portent les CVE pypi restantes (urllib3/msgpack vendored, setuptools).
#
# On interroge l'interpréteur de BASE (/usr/local/bin/python3.13) et non `python` :
# le venv copié est isolé et ne voit pas les site-packages de l'image de base,
# donc un `python -c sysconfig` renverrait /opt/venv et ne supprimerait rien.
RUN BASE_PY=/usr/local/bin/python3.13 \
    && SITE="$("$BASE_PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
    && STD="$("$BASE_PY" -c 'import sysconfig; print(sysconfig.get_paths()["stdlib"])')" \
    && rm -rf "$SITE"/pip* "$SITE"/setuptools* "$SITE"/pkg_resources* \
              "$SITE"/_distutils_hack "$SITE"/distutils-precedence.pth \
              "$STD"/ensurepip

# Garde-fou de build : échoue si du tooling de build a survécu au nettoyage.
# (une image ne doit pas pouvoir régresser silencieusement sur ce point)
RUN BASE_PY=/usr/local/bin/python3.13 \
    && "$BASE_PY" -c "import importlib.util as u; bad = [m for m in ('pip', 'setuptools', 'pkg_resources') if u.find_spec(m)]; assert not bad, 'tooling de build residuel : %s' % bad; print('OK - aucun pip/setuptools/pkg_resources restant')"

# --- 2) VERSION DE L'IMAGE ---------------------------------------------------------
# SHA du commit, injecté par la CI : docker build --build-arg IMAGE_VERSION=<sha>.
# Lu par /health (os.getenv) pour exposer la version de l'image déployée.
# Placé APRÈS l'installation des deps : un SHA nouveau n'invalide pas le cache.
ARG IMAGE_VERSION=dev
ENV IMAGE_VERSION=${IMAGE_VERSION}

# --- 3) CODE + ARTEFACTS MODÈLE -------------------------------------------------
# .dockerignore filtre déjà le superflu : model/ ne livrera que
# model.tflite, vectoriseur.joblib et metrics.json.
COPY src/ ./src/
COPY model/ ./model/

# Le package vit dans src/ (layout src), pas d'installation nécessaire
ENV PYTHONPATH=/app/src

# --- 4) REMISE À NIVEAU DES PAQUETS SYSTÈME ---------------------------------------
# La base slim est reconstruite régulièrement par l'équipe Docker, mais peut
# avoir quelques jours de retard sur le dépôt de sécurité Debian. Cette étape
# ne rattrape QUE cette fenêtre :
#   - elle ne peut pas corriger une CVE sans correctif publié (les CVE
#     restantes de l'image sont toutes « unfixed » : upgrade = effet nul) ;
#   - mesuré sur la base du jour : « 0 upgraded, 0 not upgraded ».
#
# Coût assumé : build non strictement reproductible (un rebuild à J+3 peut
# embarquer d'autres versions). D'où SECURITY_REFRESH : tant qu'il ne change
# pas, le layer reste en cache — le bumper (manuellement ou par la CI, p. ex.
# au format date) force la ré-exécution. La CI fait de toute façon un rebuild
# hebdomadaire avec --pull.
ARG SECURITY_REFRESH=2026-10-28
RUN echo "security refresh: $SECURITY_REFRESH" \
    && apt-get update \
    && apt-get upgrade -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- 5) DURCISSEMENT : utilisateur non-root ---------------------------------------
RUN useradd --create-home apiuser \
    && chown -R apiuser:apiuser /app
USER apiuser

# --- 6) RÉSEAU + SANTÉ -------------------------------------------------------------
# python:slim n'a ni curl ni wget : le healthcheck passe par urllib.
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "deeplearning_create_optimize_pushtoprod.api:app", "--host", "0.0.0.0", "--port", "8000"]
