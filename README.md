# Career Assistant — prototype personnel

> **Prototype personnel, non affilié** à l'entreprise dont le contenu carrières public sert d'exemple.
> Construit sur mon temps et mon compte AWS personnels : aucun code, aucune donnée ni aucun outil
> d'un employeur. Uniquement des données publiques (offres d'emploi publiées sur Indeed).

Assistant carrière **bilingue (FR/EN)** intégrable comme widget sur un site carrières :

- **Questions-réponses RAG** sur le contenu carrières public, avec **sources citées** sous chaque réponse ;
- **Recherche d'offres par outil** (`search_jobs`, *tool use*) → cartes cliquables ;
- **Garde-fous** : masquage des renseignements personnels (NAS, courriel, téléphone…), sujets
  interdits, détection d'injection de prompt, « je ne sais pas » plutôt qu'inventer ;
- **Escalade humaine** : bouton « parler à un recruteur » (ticket fictif) ;
- **Évaluation automatique** sur 20 questions FR/EN.

L'assistant **informe et oriente** : il ne note, ne classe ni ne présélectionne aucun candidat
(sujet bloqué par le Guardrail).

---

## Architecture

Document complet (composants, parcours d'une requête, sécurité, coûts, décisions) :
**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

```
Navigateur ── HTTPS ──► CloudFront ──┬── /*      ──► S3 privé (widget React/TS, OAC)
                                     └── /api/*  ──► API Gateway HTTP (5 req/s, rafale 10)
                                                        │
                                                        ▼
                                          Lambda Python 3.12 arm64 : FastAPI + Mangum
                                            1. Guardrail entrée  ─► Bedrock Guardrails (niveau Standard,
                                                                     profil ca.guardrail : PII, sujets, prompt attack)
                                            2. Récupération      ─► Bedrock Knowledge Base ─► S3 Vectors
                                                                     (embeddings Titan Text v2, 1024 dim.)
                                            3. Génération        ─► Bedrock Converse : Amazon Nova Lite
                                                                     (profil d'inférence ca. = Canada uniquement)
                                               └─ outil search_jobs ─► JSON d'offres publiques
                                            4. Guardrail sortie
                                            5. Historique masqué ─► DynamoDB (TTL 7 jours)
                                            6. Métriques EMF     ─► CloudWatch (logs 7 jours)

Infrastructure as Code : AWS CDK (TypeScript) · Alertes AWS Budgets 20 $ / 50 $
```

**Résidence des données** : stack en `ca-central-1` ; le modèle, le Guardrail et la base de
connaissances passent par des profils **Canada uniquement** (`ca.amazon.nova-lite-v1:0`,
`ca.guardrail.v1:0`). Aucune donnée ne sort du Canada.

## Structure du dépôt

```
backend/    FastAPI (app/), tests pytest, données publiques (data/), évaluation (eval/)
frontend/   Widget React 19 + TypeScript + Vite, tests Vitest + Testing Library
infra/      Stack AWS CDK (TypeScript) + tests d'assertions sur le template
```

## Lancer en local (sans compte AWS)

```bash
# Backend — mode offline par défaut : recherche locale, masquage regex, LLM simulé
cd backend
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # bin/ sous Linux/macOS
.venv/Scripts/python -m pytest
.venv/Scripts/uvicorn app.main:app --reload --port 8000

# Widget
cd frontend
npm install
npm run dev        # http://localhost:5180 (proxifie /api vers :8000)
npm test
```

Le **même code** tourne en local (uvicorn) et sur Lambda (Mangum) : seule la configuration
(`CA_*`, voir [config.py](backend/app/config.py)) change. `CA_MODE=aws` active Bedrock et DynamoDB.

| Route | Rôle |
|---|---|
| `GET /health` | état + mention « non affilié » |
| `POST /chat` | `{message, session_id?}` → réponse, sources citées, offres, état des garde-fous |
| `POST /escalations` | `{session_id, topic?}` → ticket fictif |

## Déployer sur AWS

Prérequis : profil AWS CLI, accès Bedrock à Amazon Nova Lite et Titan Text Embeddings v2 en
`ca-central-1`.

```bash
cd frontend && npm run build              # le widget est publié depuis frontend/dist
cd ../infra && npm install
npx cdk bootstrap                         # une seule fois par compte/région
npx cdk deploy CareerAssistant            # ~5 min ; affiche SiteUrl, ApiUrl, KnowledgeBaseId
npx cdk deploy -c modelId=ca.anthropic.claude-haiku-5-5   # changer de modèle sans toucher au code
npx cdk destroy CareerAssistant           # tout supprimer après la démo
```

Le paquet Lambda est construit **sans Docker** (wheels `manylinux2014_aarch64` via pip) ; la base de
connaissances est **réindexée automatiquement** à chaque déploiement qui modifie `backend/data/kb/`.

## Évaluation

```bash
python backend/eval/run_eval.py https://<SiteUrl>/api
```

21 questions FR/EN ([questions.json](backend/eval/questions.json)), jugement **déterministe** (pas de
LLM juge) : réponse sourcée + mot-clé attendu, offres retournées, « je ne sais pas », refus, masquage
PII, renvoi vers un recruteur pour les renseignements personnels, langue de réponse, latence.

Résultat sur le déploiement actuel (Nova Lite, 26 nov. 2026) :

| Critère | Score |
|---|---|
| Réponses sourcées | 12/12 |
| Recherche d'offres | 3/3 |
| « Je ne sais pas » hors corpus | 2/2 |
| Refus (évaluation de candidat, injection de prompt) | 2/2 |
| Masquage NAS / téléphone | 1/1 |
| Question sur ses propres renseignements → renvoi vers un recruteur | 1/1 |
| **Total** | **21/21** (19 à 21 selon les passages : Nova Lite n'est pas déterministe) |
| Langue de réponse | 21/21 |
| Latence p50 / max | 1,2 s / 4,5 s (démarrage à froid) |

L'évaluation a révélé chaque problème corrigé ci-dessous ; elle sert de test de non-régression avant
tout changement de prompt, de modèle ou de Guardrail.

## Coûts

Prix publics Bedrock `ca-central-1` (API AWS Price List, 26 nov. 2026). Hypothèse : 4 messages par
conversation, ~2 500 jetons d'entrée et ~250 de sortie par message.

| Poste | Par conversation | Démo — 1 000 conv./mois | 50 000 conv./mois |
|---|---|---|---|
| Nova Lite (0,064 $ / 0,256 $ par M jetons) | 0,0008 $ | 0,80 $ | 42 $ |
| Guardrails (PII entrée/sortie, sujets + prompt attack en entrée) | ~0,002 $ | ~2 $ | ~100 $ |
| Lambda, API Gateway, DynamoDB, CloudFront, S3 Vectors, logs | — | < 1 $ | ~10 $ |
| **Total** | | **≈ 4 $/mois** | **≈ 150 $/mois** |
| *Avec Claude Haiku 5.5 (0,11 $ / 0,55 $)* | *+0,001 $* | *≈ 5 $/mois* | *≈ 200 $/mois* |

- Au repos, la stack coûte quelques cents par mois : **pas d'OpenSearch Serverless, pas de NAT
  Gateway, pas de Kendra**.
- Avec un petit modèle, **les Guardrails coûtent plus cher que le LLM** : c'est le premier poste à
  optimiser à l'échelle (évaluer les sujets en entrée seulement, ce qui est déjà fait).
- Les prix du niveau Standard des Guardrails et de S3 Vectors sont à confirmer avant toute projection
  formelle.

## Choix techniques

| Choix | Pourquoi |
|---|---|
| Récupération systématique + boucle d'outil courte (≤ 3 tours) | Latence et coût prévisibles, sources toujours disponibles ; un agent ouvert n'apporte rien ici |
| API Converse de Bedrock | Même code pour Nova et Claude : le modèle est une variable de configuration |
| Nova Lite par défaut | Modèle le moins cher disponible au Canada ; qualité suffisante une fois le prompt cadré (19 à 21/21) |
| `ApplyGuardrail` séparé de l'appel modèle | Même politique quel que soit le modèle ; entrée bloquée **avant** tout appel LLM |
| S3 Vectors plutôt qu'OpenSearch Serverless | Aucun minimum facturé en continu |
| Historique stocké après masquage, TTL 7 jours | Minimisation et rétention courte (Loi 25) |
| Métriques EMF, aucun texte de message journalisé | Observabilité (latence, jetons, taux de « je ne sais pas », PII masquées) sans données personnelles dans les logs |
| `/api` sur la même origine via CloudFront | Pas de CORS, une seule URL |
| Lambda arm64, paquet construit sans Docker | Moins cher, build reproductible en CI |

### Ce que l'évaluation a permis de corriger

1. **Le Guardrail ne détectait rien en français** : le niveau *Classic* ne comprend que l'anglais →
   niveau **Standard** avec le profil `ca.guardrail.v1:0` (multilingue, reste au Canada).
2. **Aucune donnée personnelle détectée, même en anglais** : il faut déclarer explicitement
   `inputAction`/`outputAction` pour chaque type de PII.
3. **Faux positif** : « postes d'expert en *sinistre* » bloqué comme question sur un dossier
   d'assurance → définition du sujet précisée.
4. **Langue** : Nova répondait dans la langue des sources → consigne de langue et phrase « je ne sais
   pas » explicites dans chaque tour.
5. **Embeddings Cohere bloqués** (modèle tiers via AWS Marketplace) → Titan Text Embeddings v2.
6. **« Mon numéro de téléphone » → « je ne sais pas d'après les informations publiques »**, réponse
   trompeuse → réponse explicite (« je n'ai pas accès à vos renseignements personnels ») et renvoi
   vers un recruteur. Nova suit mieux une consigne placée dans le tour courant que dans le prompt
   système.
7. **Recherche d'offres sans cartes** après quelques échanges (constaté pendant une répétition de
   la démo) : Nova recopiait des titres de postes vus dans les sources au lieu d'appeler l'outil →
   appel d'outil forcé (`toolChoice: any`) au premier tour des questions sur les offres, pour Nova
   uniquement (Claude 5.5 refuse l'appel forcé) : 10/10 ensuite.
8. **Réponse vide** (seulement du « raisonnement » entre balises) → phrase de repli garantie : une
   bulle vide aurait aussi corrompu l'historique de la session.

## IA responsable

- **Aucune décision automatisée** sur les candidats : évaluation, classement ou prédiction d'embauche
  bloqués par le Guardrail (sujet `CandidateEvaluation`) et interdits par le prompt.
- **Transparence** : mention « prototype non affilié » et « je peux me tromper » toujours visibles ;
  sources affichées ; bandeau quand des renseignements personnels ont été masqués.
- **Ancrage** : réponses limitées aux sources récupérées, citations vérifiées côté serveur (une
  citation sans source est retirée), « je ne sais pas » sinon.
- **Données personnelles** : masquage avant le modèle et avant le stockage, rétention 7 jours,
  résidence au Canada, aucune donnée personnelle dans les logs.
- **Escalade humaine** à tout moment.

## Sécurité

- IAM au **moindre privilège** : la Lambda ne peut appeler que les deux modèles, sa base de
  connaissances, son Guardrail et sa table.
- Buckets S3 privés (accès CloudFront OAC uniquement), HTTPS imposé.
- Limitation de débit API Gateway (plafonne aussi la facture) ; alertes AWS Budgets.
- Détection d'injection de prompt (Guardrail) ; sortie du modèle nettoyée de toute balise.
- Validation des entrées (Pydantic, 2 000 caractères max).

## Limites connues

- **Corpus réduit** : 18 offres et 2 pages de synthèse issues des offres publiques. Il faudrait
  ajouter les pages du site carrières officiel (processus d'embauche, culture…) ; c'est la cause du
  raté le plus fréquent de l'évaluation (question sur le parrainage d'immigration).
- **Nova Lite** reste moins rigoureux que Claude Haiku 5.5 sur les citations ; le passage à Claude
  est prêt (`-c modelId=…`), en attente d'activation du modèle sur le compte.
- Guardrail en version `DRAFT` : en production, on publierait une version figée par déploiement.
- Pas d'authentification ni de WAF : acceptable pour une démo plafonnée, pas pour la production.
- Détection de langue par heuristique simple (FR/EN uniquement).

## Industrialisation (pistes)

Intégration à l'ATS pour des offres à jour, SSO pour les recruteurs, WAF, version de Guardrail figée,
routage de modèle (Nova pour les questions simples, Claude pour les cas complexes) mesuré sur le jeu
d'évaluation, retour 👍/👎 et revue humaine d'échantillons, tableau de bord CloudWatch, tests A/B.

---

Code : Python (FastAPI, Pydantic, boto3) · TypeScript (React 19, Vite, AWS CDK) · Tests : pytest,
Vitest, Testing Library, Jest (assertions CDK).
