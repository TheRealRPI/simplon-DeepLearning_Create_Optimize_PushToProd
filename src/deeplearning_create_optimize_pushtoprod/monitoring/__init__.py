"""
Package monitoring — le côté « analyse » du dispositif (plan §6).

Job BATCH, jamais un service (D2) : calculs lourds et ponctuels ; le hot path
de l'API ne doit pas les porter. Ces modules importent evidently / mlflow /
httpx : ils ne sont JAMAIS importés par api.py, donc jamais chargés dans
l'image de service.

Modules :
- collect    : lecture des logs JSONL + référence de dérive + paramètres ;
- drift      : rapports Evidently 0.7 (dérive entrées/prédictions) ;
- golden_set : rejeu HTTP des 400 lignes → F1 réellement servi ;
- registry   : MLflow tracking + registry (P4, bonus — D7 : optionnel) ;
- __main__   : orchestrateur CLI + codes de sortie (0/1/2/3).

Auteur : TheRealRPI
Date   : 28/10/2026
"""
