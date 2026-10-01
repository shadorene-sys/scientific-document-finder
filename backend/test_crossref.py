import requests


def rechercher_crossref(sujet, nombre=5):
    url = "https://api.crossref.org/works"

    params = {
        "query": sujet,
        "rows": nombre,
        "select": "DOI,title,author,published,container-title,URL,type"
    }

    headers = {
        "User-Agent": "ScientificDocumentFinder/1.0"
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    return data["message"]["items"]


sujet = "intelligence artificielle en médecine"

print("Recherche Crossref...")
print(f"Sujet : {sujet}")
print()

resultats = rechercher_crossref(sujet, 5)

print(f"Nombre de résultats : {len(resultats)}")
print("=" * 70)

for i, document in enumerate(resultats, start=1):

    titre = document.get("title", ["Titre inconnu"])[0]

    doi = document.get("DOI", "Pas de DOI")

    url = document.get("URL", "Pas de lien")

    type_document = document.get("type", "Type inconnu")

    auteurs = document.get("author", [])

    noms_auteurs = []

    for auteur in auteurs:
        prenom = auteur.get("given", "")
        nom = auteur.get("family", "")

        nom_complet = f"{prenom} {nom}".strip()

        if nom_complet:
            noms_auteurs.append(nom_complet)

    date_publication = document.get(
        "published",
        {}
    ).get(
        "date-parts",
        [["Date inconnue"]]
    )[0]

    annee = date_publication[0]

    revue = document.get(
        "container-title",
        ["Revue inconnue"]
    )[0]

    print(f"Résultat {i}")
    print(f"Titre       : {titre}")
    print(f"Auteurs     : {', '.join(noms_auteurs) if noms_auteurs else 'Inconnus'}")
    print(f"Année       : {annee}")
    print(f"Revue       : {revue}")
    print(f"DOI         : {doi}")
    print(f"Type        : {type_document}")
    print(f"Lien        : {url}")
    print("-" * 70)