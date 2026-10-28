"""
Log JSONL des prédictions — le côté « constat » du monitoring (D4).

Ce module écrit UNE ligne JSON par requête /predict dans un fichier JSONL sur
un volume partagé, lu plus tard par le job batch (P2). Zéro dépendance au-delà
de la stdlib : il vit dans l'image de SERVICE (A1), qui ne gagne donc aucune
librairie.

Contrat (§5.2 du plan) :
- log_prediction() NE LÈVE JAMAIS : une panne de log ne doit jamais casser
  la prédiction (A2). Toute exception est avalée ;
- open(path, "a") + une ligne par requête, JSON en UTF-8 (ensure_ascii=False) ;
- verrou de PROCESSUS (threading.Lock) : les BackgroundTasks de Starlette
  tournent dans un threadpool et peuvent logger en parallèle — sans verrou,
  leurs écritures multi-chunks s'entrelacent (bug mesuré en P3). PAS de verrou
  FICHIER : D5 — une seule réplique de l'API est assumée. Plusieurs répliques
  écriraient des lignes entrelacées (documenté dans MONITORING.md) ;
- désactivable sans redéploiement : PREDICTIONS_LOG_ENABLED=0 → no-op.

Schéma d'une ligne (§5.3) :
    {"ts", "request_id", "source", "route", "status", "motif", "latency_ms",
     "model_version", "image_version", "texte", "descripteurs", "prediction"}

    - 200 → prediction renseigné, motif null
    - 422 → prediction null, motif ("langue:fr", "trop_court"...)
    - 500 → prediction null, motif "exception"

Env :
    PREDICTIONS_LOG          chemin du fichier (défaut /data/predictions.jsonl)
    PREDICTIONS_LOG_ENABLED  "0" pour désactiver (défaut "1")

Auteur : TheRealRPI
Date   : 28/10/2026
"""

# =============================================================================
# IMPORTS
# =============================================================================

import json
import threading
from datetime import UTC, datetime
from os import getenv
from pathlib import Path
from uuid import uuid4

# =============================================================================
# CONFIGURATION — lue une fois au chargement du module
# =============================================================================

# /data = point de montage du volume partagé en compose/CI. Sans volume, le
# mkdir échoue (non-root), l'exception est avalée : aucun log, service intact.
LOG_PATH = Path(getenv("PREDICTIONS_LOG", "/data/predictions.jsonl"))

ENABLED = getenv("PREDICTIONS_LOG_ENABLED", "1") == "1"

# Version de l'image (SHA du build CI, "dev" en local) — une chute de F1 doit
# être rattachable à un release précis pour être actionnable.
IMAGE_VERSION = getenv("IMAGE_VERSION", "dev")

# ⚠️ Les BackgroundTasks de Starlette tournent dans un THREADPOOL : plusieurs
# requêtes peuvent logger EN PARALLÈLE. Sans verrou, les write() multi-chunks
# (lignes > buffer de 8 Ko) s'entrelacent → lignes corrompues (mesuré en P3 :
# 114 lignes cassées sur ~900 en démo compose). Ce verrou sérialise les
# écritures DANS le processus ; il ne protège PAS plusieurs répliques (D5).
_VERRO = threading.Lock()


# =============================================================================
# ÉCRITURE — jamais fatale, jamais bloquante
# =============================================================================


def log_prediction(
    *,
    source: str,
    route: str,
    status: int,
    texte: str | None,
    prediction: dict | None = None,
    motif: str | None = None,
    descripteurs: dict | None = None,
    latency_ms: float | None = None,
    model_version: str | None = None,
) -> None:
    """Écrit une ligne JSONL. Ne lève JAMAIS, ne bloque JAMAIS.

    Args :
        source         : "production" ou "golden_set" — le rejeu du golden set
                         ne doit JAMAIS polluter les stats de dérive ;
        route          : "/predict" ;
        status         : 200 / 422 / 500 ;
        texte          : texte nettoyé pour un 200, meilleur effort pour un 422 ;
        prediction     : {"proba", "classe", "seuil"} pour un 200, sinon None ;
        motif          : diagnostic des 422/500 ("langue:fr", "trop_court",
                         "corps_invalide", "exception"...), null pour un 200 ;
        descripteurs   : {longueur, nb_mots, langue, oov_rate} pour un 200 ;
        latency_ms     : latence mesurée côté handler, PAS en tâche de fond ;
        model_version  : version du modèle servi (metrics.json).
    """
    if not ENABLED:
        return

    ligne = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "request_id": uuid4().hex,
        "source": source,
        "route": route,
        "status": status,
        "motif": motif,
        "latency_ms": latency_ms,
        "model_version": model_version,
        "image_version": IMAGE_VERSION,
        "texte": texte,
        "descripteurs": descripteurs,
        "prediction": prediction,
    }

    try:
        # Verrou : sérialise les écritures concurrentes des BackgroundTasks
        # (threadpool Starlette) — cf. _VERRO ci-dessus.
        with _VERRO:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except Exception:
        # A2 : un échec de log (volume absent, plein, permissions) ne doit
        # JAMAIS remonter à la requête. C'est assumé et documenté.
        pass
