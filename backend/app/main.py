
from __future__ import annotations

import io
import ipaddress
import re
import socket
import threading
import time
import unicodedata
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from rapidfuzz import fuzz, process


# ============================================================
# SCIENTIFIC DOCUMENT FINDER
# VERSION 2.2 SECURE
# Sources: OpenAlex, HAL, Crossref
# ============================================================

APP_VERSION = "2.2.0 SECURE"

OPENALEX_URL = "https://api.openalex.org/works"
HAL_URL = "https://api.archives-ouvertes.fr/search/"
CROSSREF_URL = "https://api.crossref.org/works"

REQUEST_TIMEOUT = 10
PDF_TIMEOUT = 25

PER_PAGE = 25
MAX_PAGES = 3
MAX_SOURCE_RESULTS = 20

MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_ZIP_BYTES = 150 * 1024 * 1024
MAX_ZIP_DOCUMENTS = 100
MAX_REDIRECTS = 5
MAX_ACTIVE_JOBS = 100

USER_AGENT = (
    "ScientificDocumentFinder/2.2 "
    "(scientific research application)"
)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Scientific Document Finder API",
    version=APP_VERSION,
    description=(
        "Recherche scientifique rapide "
        "dans OpenAlex, HAL et Crossref."
    ),
)

app.add_middleware(
CORSMiddleware,
allow_origins=[
"http://localhost:3000",
"http://127.0.0.1:3000",
"http://192.168.43.105:3000",
"https://scientific-document-finder-frontend.onrender.com",
],
allow_credentials=True,
allow_methods=["*"],
allow_headers=["*"],

)


# ============================================================
# JOBS ZIP
# ============================================================

jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = threading.Lock()


# ============================================================
# MODÈLES
# ============================================================

class SearchRequest(BaseModel):
    sujet: str = Field(..., min_length=1, max_length=500)
    nombre: int = Field(default=10, ge=1, le=100)
    annee_min: Optional[int] = None
    annee_max: Optional[int] = None

    sources: List[str] = Field(
        default_factory=lambda: [
            "OpenAlex",
            "HAL",
            "Crossref",
        ]
    )

    type_document: str = "all"
    open_access_only: bool = True


class DownloadZipRequest(BaseModel):
    documents: List[Dict[str, Any]] = Field(
        ...,
        max_length=MAX_ZIP_DOCUMENTS,
    )


# ============================================================
# OUTILS TEXTE
# ============================================================

def normaliser_texte(texte: Any) -> str:
    if texte is None:
        return ""

    texte = unicodedata.normalize("NFKD", str(texte))
    texte = "".join(
        c for c in texte
        if not unicodedata.combining(c)
    )

    return re.sub(r"\s+", " ", texte.lower()).strip()


def nettoyer_texte(texte: Any) -> str:
    if texte is None:
        return ""

    return re.sub(r"\s+", " ", str(texte)).strip()


def extraire_annee(valeur: Any) -> Optional[int]:
    if valeur is None:
        return None

    try:
        if isinstance(valeur, int):
            return valeur if 1800 <= valeur <= 2100 else None

        match = re.search(r"(18|19|20|21)\d{2}", str(valeur))

        return int(match.group(0)) if match else None

    except (TypeError, ValueError):
        return None


def normaliser_doi(doi: Any) -> Optional[str]:
    if not doi:
        return None

    doi = str(doi).strip()

    doi = re.sub(
        r"^https?://(dx\.)?doi\.org/",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    doi = re.sub(
        r"^doi:\s*",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    doi = doi.strip().rstrip(".,;")

    return doi or None


def url_doi(doi: Any) -> Optional[str]:
    doi = normaliser_doi(doi)

    return f"https://doi.org/{doi}" if doi else None


def premier_element(valeur: Any) -> Optional[str]:
    if isinstance(valeur, list):
        valeur = valeur[0] if valeur else None

    texte = nettoyer_texte(valeur)

    return texte or None


def liste_texte(valeur: Any) -> List[str]:
    if valeur is None:
        return []

    if not isinstance(valeur, list):
        valeur = [valeur]

    resultat = []

    for item in valeur:
        if isinstance(item, dict):
            item = (
                item.get("display_name")
                or item.get("name")
                or item.get("full_name")
            )

        texte = nettoyer_texte(item)

        if texte:
            resultat.append(texte)

    return resultat


# ============================================================
# VALIDATION URL ET PROTECTION RÉSEAU
# ============================================================

def url_valide(url: Any) -> bool:
    """Vérifie la syntaxe d'une URL HTTP(S)."""

    if not isinstance(url, str) or not url or len(url) > 2048:
        return False

    try:
        parsed = urlparse(url.strip())

        if parsed.scheme.lower() not in ("http", "https"):
            return False

        if not parsed.hostname:
            return False

        if parsed.username is not None or parsed.password is not None:
            return False

        if parsed.port is not None and parsed.port not in (80, 443):
            return False

        hostname = parsed.hostname.rstrip(".").lower()

        if (
            hostname == "localhost"
            or hostname.endswith(
                (".localhost", ".local", ".internal")
            )
        ):
            return False

        return True

    except (ValueError, TypeError, UnicodeError):
        return False


def url_publique(url: str) -> bool:
    """Refuse les destinations IP non publiques."""

    if not url_valide(url):
        return False

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            return False

        try:
            adresse = ipaddress.ip_address(hostname)
            return adresse.is_global
        except ValueError:
            pass

        port = parsed.port or (
            443 if parsed.scheme.lower() == "https" else 80
        )

        resultats = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )

        if not resultats:
            return False

        for resultat in resultats:
            adresse_ip = ipaddress.ip_address(resultat[4][0])

            if not adresse_ip.is_global:
                return False

        return True

    except (ValueError, TypeError, OSError, socket.gaierror):
        return False


# ============================================================
# CORRECTION AUTOMATIQUE
# ============================================================

VOCABULAIRE = """
intelligence artificielle artificiel médecine médecin médical médicale santé
technologie technologies informatique programmation programme étudiant étudiants
formation performance apprentissage recherche scientifique science application
applications ordinateur données analyse système systèmes réseau réseaux algorithme
algorithmes automatique profond profonde neuronal neuronale diagnostic diagnostique
cancer maladie maladies patient patients clinique cliniques hôpital hôpitaux général générale
artificial intelligence medicine medical health healthcare technology computer computing
programming student students training learning research scientific data analysis system
network networks algorithm algorithms machine deep neural diagnosis disease diseases
clinical hospital hospitals nursing nurse education psychology biology economics environment
engineering social science cybersecurity software hardware database web development
"""

VOCABULAIRE_NORMALISE = {
    normaliser_texte(mot): mot
    for mot in VOCABULAIRE.split()
}


def corriger_recherche(sujet: str) -> Dict[str, Any]:
    sujet = nettoyer_texte(sujet)

    nouveaux_tokens = []
    corrections = []

    for token in sujet.split():
        match = re.match(
            r"^([^\wÀ-ÿ]*)(.*?)([^\wÀ-ÿ]*)$",
            token,
            flags=re.UNICODE,
        )

        if not match:
            nouveaux_tokens.append(token)
            continue

        prefixe, coeur, suffixe = match.groups()

        if (
            not coeur
            or len(coeur) <= 3
            or any(c.isdigit() for c in coeur)
        ):
            nouveaux_tokens.append(token)
            continue

        normalise = normaliser_texte(coeur)

        if normalise in VOCABULAIRE_NORMALISE:
            nouveaux_tokens.append(token)
            continue

        resultat = process.extractOne(
            normalise,
            VOCABULAIRE_NORMALISE.keys(),
            scorer=fuzz.ratio,
        )

        if resultat and resultat[1] >= 92:
            remplacement = VOCABULAIRE_NORMALISE[resultat[0]]
            nouveau_token = prefixe + remplacement + suffixe

            nouveaux_tokens.append(nouveau_token)

            if nouveau_token != token:
                corrections.append({
                    "avant": coeur,
                    "apres": remplacement,
                })
        else:
            nouveaux_tokens.append(token)

    sujet_corrige = " ".join(nouveaux_tokens)

    return {
        "sujet_original": sujet,
        "sujet_corrige": sujet_corrige,
        "correction_effectuee": sujet_corrige != sujet,
        "corrections": corrections,
    }


# ============================================================
# TYPES DE DOCUMENTS
# ============================================================

def normaliser_type_openalex(valeur: Any) -> str:
    texte = normaliser_texte(valeur)

    if "proceedings" in texte or "conference" in texte:
        return "conference"

    if "dissertation" in texte or "thesis" in texte:
        return "thesis"

    if "book" in texte or "chapter" in texte:
        return "book"

    if "article" in texte or texte in {
        "review", "editorial", "letter", "erratum"
    }:
        return "article"

    return "other"


def normaliser_type_hal(valeur: Any) -> str:
    texte = normaliser_texte(valeur)

    if texte in {
        "these", "hdr", "mem", "memoire", "habilitation"
    }:
        return "thesis"

    if (
        texte.startswith("comm")
        or "conference" in texte
        or "congres" in texte
    ):
        return "conference"

    if texte in {
        "ouv", "chap", "chapo", "ouvrage", "book", "bookchapter"
    }:
        return "book"

    if texte.startswith("art") or "article" in texte:
        return "article"

    return "other"


def normaliser_type_crossref(valeur: Any) -> str:
    texte = normaliser_texte(valeur)

    if "proceedings" in texte or "conference" in texte:
        return "conference"

    if "dissertation" in texte:
        return "thesis"

    if "book" in texte:
        return "book"

    if (
        "article" in texte
        or texte == "posted content"
        or "review" in texte
    ):
        return "article"

    return "other"


def filtrer_par_type(
    documents: List[Dict[str, Any]],
    type_document: str,
) -> List[Dict[str, Any]]:
    type_document = normaliser_texte(type_document)

    if type_document in ("", "all", "tous"):
        return documents

    types_valides = {
        "article", "thesis", "conference", "book", "other"
    }

    if type_document not in types_valides:
        return documents

    return [
        document for document in documents
        if document.get("type_document") == type_document
    ]


# ============================================================
# ABSTRACT OPENALEX
# ============================================================

def reconstruire_abstract(inverted_index: Any) -> str:
    if not isinstance(inverted_index, dict):
        return ""

    mots = []

    for mot, positions in inverted_index.items():
        if not isinstance(positions, list):
            continue

        for position in positions:
            try:
                mots.append((int(position), str(mot)))
            except (TypeError, ValueError):
                continue

    mots.sort(key=lambda element: element[0])

    return " ".join(mot for _, mot in mots)


# ============================================================
# OPENALEX
# ============================================================

def rechercher_openalex(sujet: str) -> List[Dict[str, Any]]:
    documents = []

    for page in range(1, MAX_PAGES + 1):
        try:
            response = requests.get(
                OPENALEX_URL,
                params={
                    "search": sujet,
                    "page": page,
                    "per-page": PER_PAGE,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 429:
                time.sleep(2)
                continue

            if response.status_code != 200:
                break

            results = response.json().get("results", [])

        except (requests.RequestException, ValueError):
            break

        if not results:
            break

        for work in results:
            titre = nettoyer_texte(
                work.get("display_name") or work.get("title")
            )

            if not titre:
                continue

            doi = normaliser_doi(work.get("doi"))
            open_access_info = work.get("open_access") or {}

            pdf_url = (
                work.get("best_oa_location") or {}
            ).get("pdf_url")

            if not pdf_url:
                for location in work.get("locations") or []:
                    if isinstance(location, dict) and location.get("pdf_url"):
                        pdf_url = location["pdf_url"]
                        break

            if not url_valide(pdf_url):
                pdf_url = None

            auteurs = []

            for authorship in work.get("authorships") or []:
                author = (authorship or {}).get("author") or {}
                nom = nettoyer_texte(author.get("display_name"))

                if nom:
                    auteurs.append(nom)

            keywords = [
                nettoyer_texte(keyword.get("display_name"))
                for keyword in work.get("keywords") or []
                if isinstance(keyword, dict) and keyword.get("display_name")
            ]

            primary_location = work.get("primary_location") or {}
            source_info = primary_location.get("source") or {}
            abstract = reconstruire_abstract(
                work.get("abstract_inverted_index")
            )

            oa_status = open_access_info.get("oa_status")

            documents.append({
                "titre": titre,
                "annee": extraire_annee(work.get("publication_year")),
                "doi": doi,
                "source": "OpenAlex",
                "open_access": bool(open_access_info.get("is_oa")),
                "oa_status": oa_status,
                "statut_oa": oa_status,
                "lien_pdf": pdf_url,
                "pdf_valide": bool(pdf_url),
                "score": 0,
                "resume": abstract,
                "abstract": abstract,
                "auteurs": auteurs,
                "journal": nettoyer_texte(
                    source_info.get("display_name")
                ) or None,
                "url": url_doi(doi) or work.get("id"),
                "keywords": keywords,
                "type_document": normaliser_type_openalex(
                    work.get("type")
                ),
            })

            if len(documents) >= MAX_SOURCE_RESULTS:
                return documents

    return documents


# ============================================================
# HAL
# ============================================================

def rechercher_hal(sujet: str) -> List[Dict[str, Any]]:
    documents = []

    champs = (
        "title_s,title_t,producedDateY_i,doiId_s,uri_s,fileMain_s,"
        "abstract_s,keyword_s,authFullName_s,journalTitle_s,docType_s"
    )

    for page in range(MAX_PAGES):
        try:
            response = requests.get(
                HAL_URL,
                params={
                    "q": sujet,
                    "rows": PER_PAGE,
                    "start": page * PER_PAGE,
                    "wt": "json",
                    "fl": champs,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 429:
                time.sleep(2)
                continue

            if response.status_code != 200:
                break

            docs = response.json().get("response", {}).get("docs", [])

        except (requests.RequestException, ValueError):
            break

        if not docs:
            break

        for item in docs:
            titre = (
                premier_element(item.get("title_s"))
                or premier_element(item.get("title_t"))
            )

            if not titre:
                continue

            doi = normaliser_doi(item.get("doiId_s"))
            uri = premier_element(item.get("uri_s"))
            file_url = premier_element(item.get("fileMain_s"))

            if file_url and not url_valide(file_url):
                file_url = None

            abstract = premier_element(item.get("abstract_s")) or ""
            auteurs = liste_texte(item.get("authFullName_s"))
            keywords = liste_texte(item.get("keyword_s"))
            journal = premier_element(item.get("journalTitle_s"))
            type_document = normaliser_type_hal(item.get("docType_s"))

            documents.append({
                "titre": titre,
                "annee": extraire_annee(item.get("producedDateY_i")),
                "doi": doi,
                "source": "HAL",
                "open_access": bool(file_url or uri),
                "oa_status": "repository",
                "statut_oa": "repository",
                "lien_pdf": file_url or uri,
                "pdf_valide": bool(file_url),
                "score": 0,
                "resume": abstract,
                "abstract": abstract,
                "auteurs": auteurs,
                "journal": journal,
                "url": url_doi(doi) or uri,
                "keywords": keywords,
                "type_document": type_document,
            })

            if len(documents) >= MAX_SOURCE_RESULTS:
                return documents

    return documents


# ============================================================
# CROSSREF
# ============================================================

def rechercher_crossref(sujet: str) -> List[Dict[str, Any]]:
    documents = []

    for page in range(MAX_PAGES):
        try:
            response = requests.get(
                CROSSREF_URL,
                params={
                    "query.bibliographic": sujet,
                    "rows": PER_PAGE,
                    "offset": page * PER_PAGE,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 429:
                time.sleep(2)
                continue

            if response.status_code != 200:
                break

            items = response.json().get("message", {}).get("items", [])

        except (requests.RequestException, ValueError):
            break

        if not items:
            break

        for item in items:
            titres = item.get("title") or []
            titre = nettoyer_texte(titres[0]) if titres else ""

            if not titre:
                continue

            doi = normaliser_doi(item.get("DOI"))

            date_source = (
                item.get("published-print")
                or item.get("published-online")
                or item.get("issued")
                or {}
            )

            date_parts = date_source.get("date-parts") or []

            try:
                annee = (
                    extraire_annee(date_parts[0][0])
                    if date_parts
                    else None
                )
            except (IndexError, TypeError):
                annee = None

            pdf_url = None

            for link in item.get("link") or []:
                if not isinstance(link, dict):
                    continue

                candidate = link.get("URL")
                content_type = normaliser_texte(
                    link.get("content-type")
                )

                if (
                    candidate
                    and (
                        "application/pdf" in content_type
                        or candidate.lower().split("?")[0].endswith(".pdf")
                    )
                    and url_valide(candidate)
                ):
                    pdf_url = candidate
                    break

            auteurs = []

            for author in item.get("author") or []:
                nom = nettoyer_texte(
                    f"{author.get('given') or ''} "
                    f"{author.get('family') or ''}"
                )

                if nom:
                    auteurs.append(nom)

            containers = item.get("container-title") or []
            journal = nettoyer_texte(containers[0]) if containers else None
            abstract = nettoyer_texte(item.get("abstract"))
            open_access = bool(pdf_url)

            documents.append({
                "titre": titre,
                "annee": annee,
                "doi": doi,
                "source": "Crossref",
                "open_access": open_access,
                "oa_status": "gold" if open_access else "closed",
                "statut_oa": "gold" if open_access else "closed",
                "lien_pdf": pdf_url,
                "pdf_valide": bool(pdf_url),
                "score": 0,
                "resume": abstract,
                "abstract": abstract,
                "auteurs": auteurs,
                "journal": journal,
                "url": url_doi(doi) or item.get("URL"),
                "keywords": [],
                "type_document": normaliser_type_crossref(
                    item.get("type")
                ),
            })

            if len(documents) >= MAX_SOURCE_RESULTS:
                return documents

    return documents


# ============================================================
# SOURCES ET DÉDOUBLONNAGE
# ============================================================

def normaliser_sources(sources: Any) -> List[str]:
    mapping = {
        "openalex": "OpenAlex",
        "hal": "HAL",
        "crossref": "Crossref",
    }

    if not sources:
        return list(mapping.values())

    resultat = []

    for source in sources:
        nom = mapping.get(normaliser_texte(source))

        if nom and nom not in resultat:
            resultat.append(nom)

    return resultat or list(mapping.values())


def rechercher_source(source: str, sujet: str) -> List[Dict[str, Any]]:
    fonctions = {
        "OpenAlex": rechercher_openalex,
        "HAL": rechercher_hal,
        "Crossref": rechercher_crossref,
    }

    return fonctions[source](sujet)


def cle_document(document: Dict[str, Any]) -> str:
    doi = normaliser_doi(document.get("doi"))

    if doi:
        return "doi:" + normaliser_texte(doi)

    titre = normaliser_texte(document.get("titre"))
    annee = document.get("annee") or ""

    return f"titre:{titre}|{annee}"


def dedoublonner(
    documents: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    uniques = {}

    for document in documents:
        cle = cle_document(document)

        if cle not in uniques:
            uniques[cle] = document
            continue

        ancien = uniques[cle]

        ancien_qualite = (
            bool(ancien.get("lien_pdf")),
            bool(ancien.get("open_access")),
            len(ancien.get("resume") or ""),
        )

        nouvelle_qualite = (
            bool(document.get("lien_pdf")),
            bool(document.get("open_access")),
            len(document.get("resume") or ""),
        )

        if nouvelle_qualite > ancien_qualite:
            uniques[cle] = document

    return list(uniques.values())


# ============================================================
# SCORE ET FILTRES
# ============================================================

def calculer_score(document: Dict[str, Any], sujet: str) -> int:
    score = 0

    requete = normaliser_texte(sujet)
    titre = normaliser_texte(document.get("titre"))
    resume = normaliser_texte(
        document.get("resume") or document.get("abstract")
    )
    keywords = normaliser_texte(
        " ".join(document.get("keywords") or [])
    )

    for mot in (m for m in requete.split() if len(m) > 2):
        if mot in titre:
            score += 8
        if mot in resume:
            score += 3
        if mot in keywords:
            score += 4

    if requete and requete in titre:
        score += 10

    if document.get("lien_pdf"):
        score += 3

    if document.get("open_access"):
        score += 3

    if document.get("doi"):
        score += 1

    if requete and titre:
        similarite = fuzz.token_set_ratio(requete, titre)

        if similarite >= 90:
            score += 8
        elif similarite >= 80:
            score += 5
        elif similarite >= 70:
            score += 2

    return score


def filtrer_par_annee(
    documents: List[Dict[str, Any]],
    annee_min: Optional[int],
    annee_max: Optional[int],
) -> List[Dict[str, Any]]:
    resultat = []

    for document in documents:
        annee = extraire_annee(document.get("annee"))

        if annee_min is not None and (
            annee is None or annee < annee_min
        ):
            continue

        if annee_max is not None and (
            annee is None or annee > annee_max
        ):
            continue

        resultat.append(document)

    return resultat


def filtrer_open_access(
    documents: List[Dict[str, Any]],
    open_access_only: bool,
) -> List[Dict[str, Any]]:
    if not open_access_only:
        return documents

    return [
        document for document in documents
        if document.get("open_access") and document.get("lien_pdf")
    ]


# ============================================================
# RECHERCHE PRINCIPALE
# ============================================================

@app.post("/search")
def search(request: SearchRequest):
    debut = time.time()
    sujet_original = nettoyer_texte(request.sujet)

    if not sujet_original:
        raise HTTPException(
            status_code=400,
            detail="Le sujet de recherche est obligatoire.",
        )

    if (
        request.annee_min is not None
        and request.annee_max is not None
        and request.annee_min > request.annee_max
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "L'année minimale doit être inférieure "
                "ou égale à l'année maximale."
            ),
        )

    correction = corriger_recherche(sujet_original)
    sujet_corrige = correction["sujet_corrige"]
    sources = normaliser_sources(request.sources)

    tous_documents = []
    erreurs_sources = []

    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        futures = {
            executor.submit(rechercher_source, source, sujet_corrige): source
            for source in sources
        }

        for future in as_completed(futures):
            source = futures[future]

            try:
                tous_documents.extend(future.result())
            except Exception as erreur:
                erreurs_sources.append({
                    "source": source,
                    "erreur": str(erreur)[:300],
                })

    documents = dedoublonner(tous_documents)
    nombre_avant_filtres = len(documents)

    documents = filtrer_par_annee(
        documents,
        request.annee_min,
        request.annee_max,
    )

    documents = filtrer_par_type(
        documents,
        request.type_document,
    )

    documents = filtrer_open_access(
        documents,
        request.open_access_only,
    )

    for document in documents:
        document["score"] = calculer_score(
            document,
            sujet_corrige,
        )

        document.setdefault("resume", document.get("abstract") or "")
        document.setdefault("abstract", document.get("resume") or "")
        document.setdefault("oa_status", document.get("statut_oa"))
        document.setdefault("statut_oa", document.get("oa_status"))
        document.setdefault("auteurs", [])
        document.setdefault("keywords", [])
        document.setdefault("type_document", "other")
        document.setdefault("pdf_valide", bool(document.get("lien_pdf")))

    documents.sort(
        key=lambda document: (
            document.get("score") or 0,
            bool(document.get("open_access")),
            bool(document.get("lien_pdf")),
            document.get("annee") or 0,
        ),
        reverse=True,
    )

    documents = documents[:request.nombre]

    return {
        "version": APP_VERSION,
        "sujet_original": correction["sujet_original"],
        "sujet_corrige": sujet_corrige,
        "correction_effectuee": correction["correction_effectuee"],
        "corrections": correction["corrections"],
        "nombre_demande": request.nombre,
        "nombre_trouve": len(documents),
        "nombre_avant_filtres": nombre_avant_filtres,
        "sources_utilisees": sources,
        "erreurs_sources": erreurs_sources,
        "temps_recherche": round(time.time() - debut, 2),
        "filtres": {
            "annee_min": request.annee_min,
            "annee_max": request.annee_max,
            "type_document": request.type_document,
            "open_access_only": request.open_access_only,
        },
        "documents": documents,
    }


# ============================================================
# ENDPOINTS DE BASE
# ============================================================

@app.get("/")
def root():
    return {
        "application": "Scientific Document Finder",
        "version": APP_VERSION,
        "status": "online",
        "sources": ["OpenAlex", "HAL", "Crossref"],
    }


@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


# ============================================================
# TÉLÉCHARGEMENT PDF SÉCURISÉ
# ============================================================

def ouvrir_url_publique(url: str):
    """Ouvre une URL en vérifiant les redirections."""

    url_courante = url

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/pdf,application/octet-stream,*/*",
    }

    for _ in range(MAX_REDIRECTS + 1):
        if not url_publique(url_courante):
            raise ValueError("URL non publique ou non autorisée.")

        response = requests.get(
            url_courante,
            headers=headers,
            timeout=(5, PDF_TIMEOUT),
            stream=True,
            allow_redirects=False,
        )

        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()

            if not location:
                raise ValueError("Redirection sans destination.")

            nouvelle_url = urljoin(url_courante, location)

            if (
                urlparse(url_courante).scheme.lower() == "https"
                and urlparse(nouvelle_url).scheme.lower() != "https"
            ):
                raise ValueError(
                    "Redirection HTTPS vers HTTP refusée."
                )

            url_courante = nouvelle_url
            continue

        if response.status_code != 200:
            status = response.status_code
            response.close()
            raise ValueError(f"Le serveur a retourné HTTP {status}.")

        return response

    raise ValueError("Nombre maximal de redirections dépassé.")


def telecharger_pdf_securise(url: str) -> bytes:
    """Télécharge un PDF avec une limite de 25 Mo."""

    response = ouvrir_url_publique(url)

    try:
        content_length = response.headers.get("Content-Length")

        if content_length:
            try:
                taille_annoncee = int(content_length)
            except (TypeError, ValueError):
                raise ValueError("Taille de PDF invalide.")

            if taille_annoncee > MAX_PDF_BYTES:
                raise ValueError("PDF supérieur à 25 Mo.")

        morceaux = []
        taille = 0

        for morceau in response.iter_content(chunk_size=64 * 1024):
            if not morceau:
                continue

            taille += len(morceau)

            if taille > MAX_PDF_BYTES:
                raise ValueError("PDF supérieur à 25 Mo.")

            morceaux.append(morceau)

        contenu = b"".join(morceaux)

        if not contenu.startswith(b"%PDF"):
            raise ValueError("Le contenu reçu n'est pas un PDF valide.")

        return contenu

    finally:
        response.close()


def verifier_pdf(url: Any) -> bool:
    """Vérifie un PDF sans conserver tout son contenu."""

    if not url_valide(url):
        return False

    try:
        response = ouvrir_url_publique(str(url))

        try:
            debut = response.raw.read(5, decode_content=True)
            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            return (
                debut.startswith(b"%PDF")
                or "application/pdf" in content_type
            )

        finally:
            response.close()

    except (requests.RequestException, ValueError, OSError):
        return False


def nom_fichier_securise(titre: Any, annee: Any = None) -> str:
    titre = nettoyer_texte(titre) or "document"

    titre = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]+',
        "_",
        titre,
    )

    titre = re.sub(r"\s+", " ", titre).strip(" .")[:140]
    titre = titre or "document"

    if annee:
        return f"{annee} - {titre}.pdf"

    return f"{titre}.pdf"


def mettre_a_jour_job(job_id: str, **valeurs: Any):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(valeurs)


def etat_job_compatible(job: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "statut": job.get("statut"),
        "message": job.get("message"),
        "etape": job.get("etape"),
        "percent": job.get("percent", 0),
        "pourcentage": job.get("pourcentage", 0),
        "completed": job.get("completed", 0),
        "documents_traites": job.get("documents_traites", 0),
        "total": job.get("total", 0),
        "total_documents": job.get("total_documents", 0),
        "download_ready": job.get("download_ready", False),
        "termine": job.get("termine", False),
        "annule": job.get("annule", False),
        "paused": job.get("paused", False),
        "erreur": job.get("erreur"),
    }


# ============================================================
# WORKER ZIP
# ============================================================

def executer_telechargement_zip(
    job_id: str,
    documents: List[Dict[str, Any]],
):
    buffer = io.BytesIO()
    total = len(documents)
    telecharges = 0
    echecs = 0
    taille_totale_pdf = 0
    erreurs_detaillees = []

    try:
        mettre_a_jour_job(
            job_id,
            status="running",
            statut="en_cours",
            etape="Préparation du téléchargement",
            message="Préparation du téléchargement...",
        )

        noms_utilises = set()

        with zipfile.ZipFile(
            buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:

            for index, document in enumerate(documents, start=1):

                # PAUSE ET ANNULATION
                while True:
                    with jobs_lock:
                        job = jobs.get(job_id)

                        if not job:
                            return

                        paused = bool(job.get("paused"))
                        cancel_event = job.get("cancel_event")
                        cancelled = (
                            cancel_event.is_set()
                            if cancel_event
                            else False
                        )

                    if cancelled:
                        mettre_a_jour_job(
                            job_id,
                            status="cancelled",
                            statut="annule",
                            message="Téléchargement annulé.",
                            etape="Annulé",
                            annule=True,
                            termine=False,
                            download_ready=False,
                        )
                        return

                    if not paused:
                        break

                    mettre_a_jour_job(
                        job_id,
                        status="paused",
                        statut="en_pause",
                        message="Téléchargement en pause.",
                        etape="En pause",
                    )

                    time.sleep(0.3)

                pdf_url = document.get("lien_pdf")
                titre = nettoyer_texte(
                    document.get("titre")
                ) or "document"
                annee = document.get("annee")

                mettre_a_jour_job(
                    job_id,
                    status="running",
                    statut="en_cours",
                    etape=f"Téléchargement {index}/{total}",
                    message=f"Téléchargement : {titre}",
                )

                raison_echec = None

                if not url_valide(pdf_url):
                    raison_echec = "Aucun lien PDF valide disponible."

                else:
                    try:
                        contenu = telecharger_pdf_securise(
                            str(pdf_url)
                        )

                        if (
                            taille_totale_pdf + len(contenu)
                            > MAX_ZIP_BYTES
                        ):
                            raise ValueError(
                                "La limite totale de 150 Mo est atteinte."
                            )

                        nom = nom_fichier_securise(titre, annee)
                        base_nom = nom
                        compteur = 2

                        while nom in noms_utilises:
                            if base_nom.lower().endswith(".pdf"):
                                nom = (
                                    base_nom[:-4]
                                    + f" ({compteur}).pdf"
                                )
                            else:
                                nom = (
                                    base_nom
                                    + f" ({compteur})"
                                )

                            compteur += 1

                        noms_utilises.add(nom)
                        archive.writestr(nom, contenu)

                        taille_totale_pdf += len(contenu)
                        telecharges += 1

                    except (
                        requests.RequestException,
                        ValueError,
                        OSError,
                    ) as erreur:
                        raison_echec = (
                            f"PDF refusé ou erreur réseau : {erreur}"
                        )

                    except Exception as erreur:
                        raison_echec = f"Erreur : {erreur}"

                if raison_echec:
                    echecs += 1
                    erreurs_detaillees.append(
                        f"{titre} — {raison_echec}"[:500]
                    )

                pourcentage = (
                    int(index / total * 100)
                    if total
                    else 100
                )

                mettre_a_jour_job(
                    job_id,
                    documents_traites=index,
                    completed=index,
                    percent=pourcentage,
                    pourcentage=pourcentage,
                    telecharges=telecharges,
                    pdf_telecharges=telecharges,
                    echecs=echecs,
                    pdf_echecs=echecs,
                )

        # Ne jamais créer un ZIP vide comme un succès.
        if telecharges == 0:
            message = (
                f"Aucun PDF n'a pu être téléchargé sur {total} document(s). "
                "Le ZIP vide n'a pas été créé. Vérifiez les liens PDF."
            )

            mettre_a_jour_job(
                job_id,
                status="error",
                statut="erreur",
                message=message,
                etape="Aucun PDF téléchargé",
                erreur=message,
                percent=100,
                pourcentage=100,
                completed=total,
                documents_traites=total,
                telecharges=0,
                pdf_telecharges=0,
                echecs=echecs,
                pdf_echecs=echecs,
                download_ready=False,
                termine=False,
            )
            return

        zip_data = buffer.getvalue()

        message = (
            f"Téléchargement terminé : {telecharges} PDF téléchargé(s)"
        )

        if echecs:
            message += (
                f", {echecs} document(s) non téléchargé(s)."
            )

        with jobs_lock:
            if job_id not in jobs:
                return

            jobs[job_id].update({
                "zip_data": zip_data,
                "status": "completed",
                "statut": "termine",
                "message": message,
                "etape": "Terminé",
                "percent": 100,
                "pourcentage": 100,
                "completed": total,
                "documents_traites": total,
                "telecharges": telecharges,
                "pdf_telecharges": telecharges,
                "echecs": echecs,
                "pdf_echecs": echecs,
                "erreurs_detaillees": erreurs_detaillees[:20],
                "download_ready": True,
                "termine": True,
                "annule": False,
                "erreur": None,
            })

    except Exception as erreur:
        mettre_a_jour_job(
            job_id,
            status="error",
            statut="erreur",
            message="Une erreur est survenue pendant la création du ZIP.",
            etape="Erreur",
            erreur=str(erreur)[:1000],
            termine=False,
            download_ready=False,
        )

    finally:
        buffer.close()


# ============================================================
# POST /download-zip
# ============================================================

@app.post("/download-zip")
def download_zip(request: DownloadZipRequest):
    documents = request.documents

    if not documents:
        raise HTTPException(
            status_code=400,
            detail="Aucun document à télécharger.",
        )

    if len(documents) > MAX_ZIP_DOCUMENTS:
        raise HTTPException(
            status_code=400,
            detail="Maximum 100 documents par téléchargement ZIP.",
        )

    with jobs_lock:
        active_jobs = sum(
            1
            for job in jobs.values()
            if job.get("status") in {
                "starting", "running", "paused"
            }
        )

        if active_jobs >= MAX_ACTIVE_JOBS:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Trop de téléchargements sont en cours. "
                    "Réessayez plus tard."
                ),
            )

        job_id = str(uuid.uuid4())
        cancel_event = threading.Event()

        jobs[job_id] = {
            "job_id": job_id,
            "status": "starting",
            "statut": "demarrage",
            "message": "Démarrage du téléchargement...",
            "etape": "Préparation",
            "percent": 0,
            "pourcentage": 0,
            "completed": 0,
            "documents_traites": 0,
            "telecharges": 0,
            "pdf_telecharges": 0,
            "echecs": 0,
            "pdf_echecs": 0,
            "total": len(documents),
            "total_documents": len(documents),
            "download_ready": False,
            "termine": False,
            "annule": False,
            "paused": False,
            "erreur": None,
            "zip_data": None,
            "cancel_event": cancel_event,
        }

    thread = threading.Thread(
        target=executer_telechargement_zip,
        args=(job_id, documents),
        daemon=True,
    )

    thread.start()

    return {
        "job_id": job_id,
        "status": "starting",
        "statut": "demarrage",
        "message": "Téléchargement démarré.",
    }


# ============================================================
# GET /download-progress/{job_id}
# ============================================================

@app.get("/download-progress/{job_id}")
def download_progress(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job introuvable.",
            )

        return etat_job_compatible(job)


# ============================================================
# GET /download-zip/{job_id}
# ============================================================

@app.get("/download-zip/{job_id}")
def get_download_zip(job_id: str):
    limite = time.time() + 120

    while time.time() < limite:
        with jobs_lock:
            job = jobs.get(job_id)

            if not job:
                raise HTTPException(
                    status_code=404,
                    detail="Job introuvable.",
                )

            zip_data = job.get("zip_data")

            if zip_data is not None:
                break

            if job.get("status") in {"cancelled", "error"}:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        job.get("message")
                        or "Le téléchargement n'est pas disponible."
                    ),
                )

        time.sleep(0.25)

    else:
        raise HTTPException(
            status_code=409,
            detail="Le fichier ZIP n'est pas encore prêt.",
        )

    return Response(
        content=zip_data,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                'attachment; filename="scientific_documents.zip"'
            )
        },
    )


# ============================================================
# POST /download-pause/{job_id}
# ============================================================

@app.post("/download-pause/{job_id}")
def pause_download(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job introuvable.",
            )

        if (
            job.get("termine")
            or job.get("annule")
            or job.get("status") in {"error", "cancelled"}
        ):
            return etat_job_compatible(job)

        job.update({
            "paused": True,
            "status": "paused",
            "statut": "en_pause",
            "message": "Téléchargement en pause.",
            "etape": "En pause",
        })

        return etat_job_compatible(job)


# ============================================================
# POST /download-resume/{job_id}
# ============================================================

@app.post("/download-resume/{job_id}")
def resume_download(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job introuvable.",
            )

        if (
            job.get("termine")
            or job.get("annule")
            or job.get("status") in {"error", "cancelled"}
        ):
            return etat_job_compatible(job)

        job.update({
            "paused": False,
            "status": "running",
            "statut": "en_cours",
            "message": "Téléchargement repris.",
        })

        return etat_job_compatible(job)


# ============================================================
# POST /download-cancel/{job_id}
# ============================================================

@app.post("/download-cancel/{job_id}")
def cancel_download(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job introuvable.",
            )

        cancel_event = job.get("cancel_event")

        if cancel_event:
            cancel_event.set()

        job.update({
            "paused": False,
            "status": "cancelled",
            "statut": "annule",
            "message": "Annulation demandée.",
            "etape": "Annulation",
            "annule": True,
            "download_ready": False,
        })

        return etat_job_compatible(job)