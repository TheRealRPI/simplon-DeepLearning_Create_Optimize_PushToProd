"""
MLflow tracking + registry — la « mémoire » du dispositif (P4, bonus, D7).

Pourquoi MLflow alors que le tracking n'était pas indispensable :
Evidently détecte la dérive mais ne GARDE rien — chaque rapport serait jetable
et l'évolution des métriques au fil des exécutions invisible. MLflow rend le
cycle MLOps complet défendable à l'oral : chaque exécution du job devient une
run (paramètres, métriques, rapports en artefacts), et le modèle servi est
journalisé en pyfunc RECHARGEABLE.

Trois briques, une seule porte d'entrée (tracer_et_enregistrer) :
1. TRACKING — chaque job : métriques golden set + dérive, seuils en params,
   rapports HTML/JSON en artefacts (l'UI les affiche et les télécharge) ;
2. REGISTRY — le pyfunc TFLite (LiteRT + vectoriseur + nettoyer_texte)
   journalisé + register UNIQUEMENT si cette version du modèle n'y est pas
   déjà : les versions du registry s'alignent sur metrics.json:model_version ;
3. PARITÉ (A8) — après chaque register, le pyfunc est RECHARGÉ et comparé au
   modèle servi (model_loader) sur 5 textes : un registry qu'on ne recharge
   pas n'est qu'une liste de noms (plan §8.2).

D7 : ce module est OPTIONNEL — si le tracking échoue, le verdict du job
(dérive / golden set) reste la seule source d'alerte, et la CI passe
--no-mlflow.

Env :
    MLFLOW_TRACKING_URI   ex. sqlite:////data/mlflow/mlflow.db (compose)
    MLFLOW_ARTIFACTS_DIR  stockage des artefacts (défaut /data/mlflow/artifacts)

> ⚠️ L'emplacement des artefacts est passé EXPLICITEMENT à la création de
> l'expérience : sans serveur, le défaut serait ./mlruns dans le CWD —
> éphémère dans un conteneur `compose run --rm` (tout serait perdu).

Auteur : TheRealRPI
Date   : 28/10/2026
"""

# =============================================================================
# IMPORTS
# =============================================================================

from datetime import datetime
from os import getenv
from pathlib import Path

import joblib
import mlflow
import pandas as pd
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from ..model_loader import model_loader
from ..preprocessing import nettoyer_texte

# =============================================================================
# CONSTANTES
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = PROJECT_ROOT / "model"
MODEL_TFLITE = MODEL_DIR / "model.tflite"
VECTORIZER = MODEL_DIR / "vectoriseur.joblib"
REFERENCE_CSV = MODEL_DIR / "reference.csv"

EXPERIMENT = "film-classifier"
MODELE = "film-classifier"

# Tolérance de parité : même interpréteur TFLite, même vectoriseur → les
# probabilités doivent être identiques au flottant près.
TOLERANCE_PARITE = 1e-6


# =============================================================================
# ERREUR
# =============================================================================


class RegistryError(Exception):
    """Échec du tracking/registry — attrapé par __main__ (D7), jamais fatal au job."""


# =============================================================================
# WRAPPER PYFUNC — le modèle servi, rechargeable depuis le registry
# =============================================================================


class FilmClassifier(mlflow.pyfunc.PythonModel):
    """Wrapper pyfunc du modèle servi (LiteRT + TF-IDF).

    Le nettoyage (`nettoyer_texte`) est appliqué ICI — choix documenté : le
    pyfunc est auto-suffisant et strictement équivalent à l'artefact servi
    par l'API (validateur Pydantic → model_loader.predict), ce que la parité
    (A8) vérifie. L'interpréteur TFLite a une entrée de batch 1 : inférence
    ligne par ligne.
    """

    def load_context(self, context) -> None:
        from ai_edge_litert.interpreter import Interpreter

        self.interpreteur = Interpreter(model_path=context.artifacts["tflite"])
        self.interpreteur.allocate_tensors()
        self.vectoriseur = joblib.load(context.artifacts["vectorizer"])
        self.entree = self.interpreteur.get_input_details()[0]
        self.sortie = self.interpreteur.get_output_details()[0]

    # ⚠️ log_model() INFÈRE LA SIGNATURE en exécutant predict() AVANT le dump
    # cloudpickle — l'instance porte alors l'interpréteur TFLite, un objet
    # NATIF non sérialisable (mesuré : "cannot pickle InterpreterWrapper").
    # On exclut tout l'état chargé : au rechargement, load_context() le
    # reconstruit depuis les artefacts — c'est exactement son rôle.
    def __getstate__(self):
        return {k: v for k, v in self.__dict__.items()
                if k not in ("interpreteur", "vectoriseur", "entree", "sortie")}

    def __setstate__(self, etat) -> None:
        self.__dict__.update(etat)

    def predict(self, context, model_input: pd.DataFrame) -> pd.DataFrame:
        probas: list[float] = []
        for texte in model_input["texte"].tolist():
            propre = nettoyer_texte(str(texte))
            x = self.vectoriseur.transform([propre]).toarray().astype("float32")
            self.interpreteur.set_tensor(self.entree["index"], x.reshape(1, -1))
            self.interpreteur.invoke()
            probas.append(float(self.interpreteur.get_tensor(self.sortie["index"])[0][0]))
        return pd.DataFrame({"proba": probas})


# =============================================================================
# TRACKING — l'expérience, la run
# =============================================================================


def _experiment_id(client: MlflowClient, artefacts_dir: Path) -> str:
    """Crée l'expérience si besoin, avec un emplacement d'artefacts EXPLICITE."""
    existante = client.get_experiment_by_name(EXPERIMENT)
    if existante is not None:
        return existante.experiment_id
    artefacts_dir.mkdir(parents=True, exist_ok=True)
    return client.create_experiment(EXPERIMENT, artifact_location=artefacts_dir.as_uri())


def _tracer(parametres: dict, golden: dict, resultat_drift: dict | None, rejets: dict, n_production: int) -> None:
    """Journalise l'exécution : params (seuils + versions), metrics, artefacts."""
    mlflow.log_params(
        {
            "fenetre_jours": parametres["fenetre_jours"],
            "fenetre_min_lignes": parametres["fenetre_min_lignes"],
            "drift_share_max": parametres["drift_share_max"],
            "value_drift_seuil": parametres["value_drift_seuil"],
            "oov_rate_max": parametres["oov_rate_max"],
            "f1_minimum": parametres["f1_minimum"],
            "f1_reference_golden_set": parametres["f1_reference_golden_set"],
            "model_version": model_loader.metrics["model_version"],
            "image_version": getenv("IMAGE_VERSION", "dev"),
        }
    )

    metriques: dict[str, float] = {
        "golden_set_f1": golden["f1"],
        "golden_set_accuracy": golden["accuracy"],
        "golden_set_ecart_vs_reference": golden["ecart_vs_reference"],
        "golden_set_n_erreurs": golden["n_erreurs"],
        "n_production": n_production,
        "n_rejets": sum(rejets.values()),
    }
    if resultat_drift is not None:
        metriques["derive"] = 1.0 if resultat_drift["derive"] else 0.0
        metriques["drift_share_calibre"] = resultat_drift["resume"]["share_calibre"]
    mlflow.log_metrics(metriques)

    # Les rapports deviennent des artefacts : visibles et téléchargeables dans l'UI
    for cle in ("rapport_json", "rapport_classification_html"):
        chemin = golden.get(cle)
        if chemin and Path(chemin).exists():
            mlflow.log_artifact(chemin, artifact_path="rapports")
    if resultat_drift is not None:
        for cle in ("rapport_html", "rapport_json"):
            chemin = resultat_drift.get(cle)
            if chemin and Path(chemin).exists():
                mlflow.log_artifact(chemin, artifact_path="rapports")


# =============================================================================
# REGISTRY + PARITÉ
# =============================================================================


def _enregistrer_modele_si_necessaire(client: MlflowClient) -> None:
    """Journalise + register le pyfunc SI cette version du modèle n'y est pas.

    Les versions du registry s'alignent sur metrics.json:model_version —
    un register à chaque run spamerait des versions identiques.
    """
    version_modele = model_loader.metrics["model_version"]
    try:
        versions = client.search_model_versions(f"name='{MODELE}'")
    except MlflowException:
        versions = []  # le modèle n'existe pas encore dans le registry

    if any(v.tags.get("model_version") == version_modele for v in versions):
        print(f"ℹ️ Registry : {MODELE} pour la version {version_modele} déjà enregistré")
        return

    print(f"▶️ Registry : journalisation pyfunc de {MODELE} (version modèle {version_modele})")
    # MLflow 3 : log_model retourne un ModelInfo — l'URI est .model_uri
    # (formats models:/<model_id>), utilisable pour register ET load.
    model_info = mlflow.pyfunc.log_model(
        name=MODELE,
        python_model=FilmClassifier(),
        artifacts={"tflite": str(MODEL_TFLITE), "vectorizer": str(VECTORIZER)},
        pip_requirements=["ai-edge-litert", "joblib", "scikit-learn", "pandas"],
        input_example=pd.DataFrame({"texte": ["A family moves into an old mansion in the countryside."]}),
    )
    model_uri = model_info.model_uri
    version = mlflow.register_model(model_uri, MODELE)
    client.set_model_version_tag(MODELE, version.version, "model_version", version_modele)
    print(f"✅ Registry : {MODELE} v{version.version} enregistré (tag model_version={version_modele})")

    _verifier_parite(model_uri)


def _verifier_parite(model_uri: str, n_textes: int = 5) -> None:
    """A8 — le pyfunc rechargé doit prédire comme le modèle servi, sinon il est décoratif."""
    df = pd.read_csv(REFERENCE_CSV)
    echantillon = df.iloc[:: max(1, len(df) // n_textes)].head(n_textes)

    pyfunc = mlflow.pyfunc.load_model(model_uri)
    probas_registry = pyfunc.predict(
        pd.DataFrame({"texte": echantillon["resume"].astype(str)})
    )["proba"].tolist()

    for resume, proba_registry in zip(echantillon["resume"], probas_registry, strict=True):
        # Ce que sert l'API : texte nettoyé (validateur) → model_loader.predict
        proba_serve = model_loader.predict(nettoyer_texte(str(resume)))
        if abs(proba_serve - proba_registry) > TOLERANCE_PARITE:
            raise RegistryError(
                f"Parité rompue : servi={proba_serve} vs registry={proba_registry} "
                f"pour « {str(resume)[:60]}… » — le pyfunc n'est PAS le modèle servi"
            )
    print(f"✅ Parité (A8) : {n_textes}/{n_textes} prédictions identiques registry ↔ modèle servi")


# =============================================================================
# PORTE D'ENTRÉE — appelée par __main__ quand --no-mlflow est absent
# =============================================================================


def tracer_et_enregistrer(
    parametres: dict, golden: dict, resultat_drift: dict | None, rejets: dict, n_production: int
) -> None:
    """Une run par exécution du job : tracking + registry + parité.

    Lève RegistryError en cas d'échec — __main__ l'attrape (D7) : le verdict
    du monitoring (dérive / golden set) reste la seule source d'alerte.
    """
    uri = getenv("MLFLOW_TRACKING_URI")
    if not uri:
        raise RegistryError("MLFLOW_TRACKING_URI non défini — lancer avec --no-mlflow ou configurer l'URI")
    artefacts_dir = Path(getenv("MLFLOW_ARTIFACTS_DIR", "/data/mlflow/artifacts"))

    mlflow.set_tracking_uri(uri)
    artefacts_dir.mkdir(parents=True, exist_ok=True)
    client = MlflowClient()

    with mlflow.start_run(
        experiment_id=_experiment_id(client, artefacts_dir),
        run_name=f"monitoring {datetime.now():%Y-%m-%d %H:%M}",
    ) as run:
        _tracer(parametres, golden, resultat_drift, rejets, n_production)
        _enregistrer_modele_si_necessaire(client)
        print(f"✅ Tracking MLflow : run {run.info.run_id} journalisée (params + metrics + artefacts)")
