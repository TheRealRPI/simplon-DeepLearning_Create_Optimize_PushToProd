# FICHE PLAN VS RÉEL

> Synthèse d'une page : charges, coûts et jalons — prévus au PLAN.md vs constatés.
>
> Projet : DeepLearning_Create_Optimize_PushToProd | Auteur : TheRealRPI | 27/10/2026

---

## Charges (1 j = 6h30 effectives)

| Phase | Estimé (j) | Réel (j) | Écart |
|---|---|---|---|
| 0 - Mise en place | 0,20 | 0,12 | -0,08 |
| 1 - Notebook (8 parties) | 1,80 | 1,27 | -0,53 |
| 2 - API + tests + qualité | 0,55 | 1,00 | **+0,45** |
| 3 - Conteneurisation | 0,25 | 0,16 | -0,09 |
| 4 - CI/CD GitHub Actions | 0,45 | 0,30 | -0,15 |
| 5 - Déploiement Azure | 0,50 | 0,30 | -0,20 |
| 6 - Gestion des versions | 0,20 | 0,16 | -0,04 |
| 7 - Fin de vie et ménage | 0,25 | 0,15 | -0,10 |
| 8 - Documentation finale | 0,80 | 0,23 | -0,57 |
| **TOTAL** | **5,00** | **3,69** | **-1,31** |

**Livré le 27/10** — un jour avant la deadline (28/10 17h).

## Coûts Azure

| | Prévu (PLAN.md § 2.4) | Réel (FIN_DE_VIE § 5) |
|---|---|---|
| Registre ACR (Basic) | ~5 €/mois | ~4,40 €/mois, vécu ~6 h |
| Container App (1 vCPU, 2 Go) | ~30-50 €/mois en charge continue | facturée **à l'usage** (~0,35 €/M requêtes) |
| **Coût total du projet** | **~5-10 €** | **~0,04 €** (au pire ~0,15 €) |

## Jalons

J0 à J7 tous atteints. J5, J6 et J7 en avance (production en ligne vers 11h au lieu de 15h30 ; ménage exécuté le 27/10 après-midi au lieu du 28/10 matin).

## Réflexions

- **Seule la phase 2 dérape (+0,45 j)** : validation Pydantic (détection de langue, longueurs) et suite pytest (~30 tests) sous-estimées — l'avance de la phase 1 (-0,53 j) l'a absorbée.
- **Coûts** : tarif du registre bien estimé, mais modèle de facturation de la Container App erroné (à l'usage par requête, pas en charge continue). Le ménage fait le jour même (~24 h d'existence des ressources) a réduit la facture à ~0,04 €.
- **La barrière qualité a servi** : test négatif volontaire validé en CI (run #3 rouge), aucun modèle dégradé n'a pu partir en production.
- **Risque R10** (planning sans marge) non matérialisé : le projet finit avec **1,31 j d'avance** et tous les livrables présents.

---

*Sources : PLAN.md § 8 (charges) · FIN_DE_VIE.md § 5 (coûts) · JOURNAL_DES_VERSION.md (jalons).*
