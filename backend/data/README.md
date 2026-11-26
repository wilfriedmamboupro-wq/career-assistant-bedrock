# Données (publiques uniquement)

- `jobs.json` : 10–20 offres **publiques** recopiées à la main depuis le site carrières
  (champs : `id`, `title`, `city`, `language` = fr|en|bilingual, `url`, `summary`).
- `kb/*.md` : pages carrières publiques en Markdown. Première(s) ligne(s) :
  `title: ...` et `source_url: ...`. Ces fichiers sont aussi ceux envoyés dans S3
  pour la Knowledge Base (avec un `<fichier>.metadata.json` par document).

Aucun scraping massif, aucune donnée personnelle, aucune donnée d'employeur.
