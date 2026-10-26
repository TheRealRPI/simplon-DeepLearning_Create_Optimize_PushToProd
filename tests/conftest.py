"""
Fixtures partagées pour les tests de l'API.

Chargées automatiquement par pytest (pas besoin d'importer).
"""

import pytest
from fastapi.testclient import TestClient

from deeplearning_create_optimize_pushtoprod.api import app


# =============================================================================
# FIXTURE PRINCIPALE — Client de test
# =============================================================================


@pytest.fixture(scope="session")
def client() -> TestClient:
    """
    Client de test FastAPI.

    scope="session" : le client (et donc le modèle) est créé UNE SEULE fois
    pour toute la session pytest, pas pour chaque test.

    Le `with` déclenche le lifespan (chargement du modèle au démarrage).
    """
    with TestClient(app) as test_client:
        yield test_client


# =============================================================================
# FIXTURES — Textes d'exemple
# =============================================================================


@pytest.fixture
def texte_comedie() -> str:
    """Résumé de film comique en anglais (assez long pour passer la validation)."""
    return (
        "Seven year-old Albert is the son of a Las Vegas circus performer. When she is killed in a car "
        "wreck, Albert is sent to live with his mother's foster sister, Harriet Franklin, a no-nonsense "
        "businesswoman struggling in New Jersey. Albert hates it with the dour Harriet, but takes refuge "
        "in the company of Bogus, a flamboyant, gentle, loving, and altogether imaginary Frenchman. With "
        "Bogus's help, Albert can perhaps come to terms with his mother's death, and Harriet with her own "
        "loss of childhood innocence."
    )


@pytest.fixture
def texte_horreur() -> str:
    """Résumé de film d'horreur en anglais (assez long pour passer la validation)."""
    return (
        "A family moves into an old mansion deep in the countryside. Strange noises echo through the "
        "halls at night, and the walls seem to bleed when nobody is watching. One by one, the children "
        "vanish without a trace, and the mother discovers an ancient curse buried beneath the basement "
        "floor. As the blood moon rises, she realizes the house has been waiting for her family all along."
    )


@pytest.fixture
def texte_francais() -> str:
    """Résumé en français — doit être rejeté par la validation (langue non anglaise)."""
    return (
        "Une famille s'installe dans un vieux manoir à la campagne. Des bruits étranges résonnent dans "
        "les couloirs pendant la nuit et les murs semblent saigner. Les enfants disparaissent un par un, "
        "et la mère découvre une ancienne malédiction enterrée sous le sol de la cave."
    )
