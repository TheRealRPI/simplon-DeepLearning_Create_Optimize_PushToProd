# PROCÉDURE DE MISE EN PRODUCTION

> Déploiement de l'API de classification de résumés de films (horreur vs comédie) sur
> Azure Container Apps, à partir de l'image Docker publiée par la CI GitHub Actions.
>
> Projet : DeepLearning_Create_Optimize_PushToProd | Auteur : TheRealRPI | Dernière mise à jour : 27/10/2026

---

## 1. Principe

Le déploiement est **manuel** : le compte Azure formation (rôle Contributeur) interdit le CD
automatisé, c'est un choix imposé par le brief. La CI construit et publie l'image ; l'opérateur
pointe ensuite la Container App sur cette image, puis vérifie le service en ligne.

```
push master ──► job test   (barrière qualité + pytest)
                └─► job image   (build Docker + smoke test conteneur)
                       └─► job publier  (push ACR : film-api:<sha7>)
                              └─► az containerapp update   ← MANUEL (cette procédure)
                                     └─► vérifications publiques + journal
```

Deux garanties héritées de la CI :

- **Tag d'image = SHA court du commit (7 caractères)** : chaque version déployée reste
  traçable vers un commit exact, et les anciennes images restent dans l'ACR (rollback possible).
- **Barrière qualité** (`config.yaml`) : F1 ≥ 0,83 et test_size ≥ 400 — un modèle dégradé
  fait rougir le job `test`, l'image n'est jamais publiée.

## 2. Ressources (valeurs du projet)

| Élément | Valeur |
|---|---|
| Registre ACR (Basic, utilisateur admin activé) | `rpicontainerregistries.azurecr.io` |
| Image Docker | `film-api:<sha7-du-commit>` |
| Azure Container App (1 vCPU, 2 Go RAM, ingress externe) | `rpi-movies-classificator` |
| Resource group | `rpierronRG` |
| Secrets GitHub (environment `AzureContainerRegistries`) | `ACR_SERVER`, `ACR_USERNAME`, `ACR_PASSWORD` |
| URL publique | donnée par la commande `az containerapp show` ci-dessous |

> **Fin de vie :** les ressources listées ci-dessus ont été **supprimées le
> 27/10/2026** après la démonstration (registre, Container App, environnement,
> environment GitHub — voir `FIN_DE_VIE.md`), à l'exception du groupe
> `rpierronRG`, conservé (partagé). Cette procédure est conservée à titre de
> référence.

## 3. Déploiement d'une nouvelle version

### Étape 1 — Pousser le code et attendre les 3 jobs verts

```bash
git push origin master
```

Vérifier dans l'onglet **Actions** du dépôt : les jobs `test` → `image` → `publier` sont
verts (le job `publier` ne s'exécute que sur un push `master`, jamais sur une PR), puis
relever le **SHA court** du commit (7 premiers caractères de son hash).

### Étape 2 — Déployer l'image sur la Container App

```bash
az containerapp update --name rpi-movies-classificator --resource-group rpierronRG \
  --image rpicontainerregistries.azurecr.io/film-api:<sha7-du-commit>
```

### Étape 3 — Vérifier le service en production

Sur `https://<url-publique>` :

1. **Santé + version déployée** : `GET /health` → `"status": "ok"` et `version_image`
   **égal au SHA déployé** — c'est la preuve que la bonne image tourne (SHA injecté au build).
2. **Prédiction nominale** : `POST /predict` avec le JSON `{"texte": "Seven year-old
   Albert is the son of a Las Vegas circus performer. When she is killed in a car wreck,
   Albert is sent to live with his mother foster sister, Harriet Franklin, a no-nonsense
   businesswoman struggling in New Jersey."}` → HTTP 200, réponse
   `{"classe": "0 : comédie", "probabilite": ..., "version": ..., "type_modele": "tflite"}`.
3. **Cas d'erreur (validation Pydantic)** : texte de moins de 42 caractères → HTTP 422 ;
   texte en français → HTTP 422 (l'API n'accepte que l'anglais).

### Étape 4 — Tracer le déploiement

Ajouter une ligne dans `Gestion-de-projet/JOURNAL_DES_VERSION.md` (section « Versions
déployées en production ») : date, identifiant du commit, tag de l'image, changement, résultat.

## 4. Retour arrière (rollback)

Les images étant taguées par SHA et conservées dans l'ACR, revenir en arrière consiste
à redéployer le tag de la version précédente :

```bash
az containerapp update --name rpi-movies-classificator --resource-group rpierronRG \
  --image rpicontainerregistries.azurecr.io/film-api:<sha7-de-la-version-précédente>
```

Vérifier `GET /health` : `version_image` doit afficher l'ancien SHA. Consigner le rollback
dans le journal des versions.

## 5. Diagnostic (si /health ne répond pas)

```bash
az containerapp logs show --name rpi-movies-classificator --resource-group rpierronRG
```

| Symptôme | Cause probable | Remède |
|---|---|---|
| Conteneur en redémarrage bouclé | Mémoire insuffisante (modèle TFLite) | Vérifier 2 Go RAM alloués, consulter les logs |
| Image introuvable | Job `publier` rouge ou SHA erroné | Re-pousser le commit / corriger le tag |
| /health lent puis OK | Chargement du modèle > start-period | Normal au premier démarrage, patienter |

---

*Document rédigé le 27/10/2026 par TheRealRPI — procédure appliquée avec succès le 27/10 (jalons J5 et J6 du PLAN.md).*
