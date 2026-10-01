from __future__ import annotations

import io
import re
import time
import uuid
import zipfile
import threading
import unicodedata

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from rapidfuzz import fuzz, process


# ============================================================
# SCIENTIFIC DOCUMENT FINDER
# VERSION 2.1 FAST
#
# Sources :
#   - OpenAlex
#   - HAL
#   - Crossref
#
# Recherche rapide :
#   - sources en parallèle
#   - aucune vérification PDF pendant la recherche
#   - vérification PDF uniquement pendant le ZIP
# ============================================================


APP_VERSION = "2.1.0 FAST"

OPENALEX_URL = "https://api.openalex.org/works"
HAL_URL = "https://api.archives-ouvertes.fr/search/"
CROSSREF_URL = "https://api.crossref.org/works"

REQUEST_TIMEOUT = 10
PDF_TIMEOUT = 25

PER_PAGE = 25
MAX_PAGES = 3
MAX_SOURCE_RESULTS = 20

USER_AGENT = (
    "ScientificDocumentFinder/2.1 "
    "(scientific research application)"
)


# ============================================================
# APPLICATION FASTAPI
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# JOBS DE TÉLÉCHARGEMENT ZIP
# ============================================================

jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = threading.Lock()


# ============================================================
# MODÈLES
# ============================================================

class SearchRequest(BaseModel):
    sujet: str = Field(
        ...,
        min_length=1,
    )

    nombre: int = Field(
        default=10,
        ge=1,
        le=100,
    )

    annee_min: Optional[int] = None
    annee_max: Optional[int] = None

    # Les trois sources sont utilisées par défaut.
    # Le frontend peut toujours envoyer une sélection
    # s'il souhaite utiliser les cases à cocher.
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
    documents: List[Dict[str, Any]]


# ============================================================
# OUTILS TEXTE
# ============================================================

def normaliser_texte(
    texte: Any,
) -> str:
    if texte is None:
        return ""

    texte = str(texte)

    texte = unicodedata.normalize(
        "NFKD",
        texte,
    )

    texte = "".join(
        caractere
        for caractere in texte
        if not unicodedata.combining(
            caractere
        )
    )

    texte = texte.lower()

    texte = re.sub(
        r"\s+",
        " ",
        texte,
    )

    return texte.strip()


def nettoyer_texte(
    texte: Any,
) -> str:
    if texte is None:
        return ""

    texte = str(texte)

    texte = re.sub(
        r"\s+",
        " ",
        texte,
    )

    return texte.strip()


def extraire_annee(
    valeur: Any,
) -> Optional[int]:
    if valeur is None:
        return None

    try:
        if isinstance(
            valeur,
            int,
        ):
            if 1800 <= valeur <= 2100:
                return valeur

            return None

        match = re.search(
            r"(18|19|20|21)\d{2}",
            str(valeur),
        )

        if match:
            return int(
                match.group(0)
            )

    except Exception:
        pass

    return None


def normaliser_doi(
    doi: Any,
) -> Optional[str]:
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

    doi = doi.strip().rstrip(
        ".,;"
    )

    return doi or None


def url_doi(
    doi: Any,
) -> Optional[str]:
    doi = normaliser_doi(
        doi
    )

    if not doi:
        return None

    return (
        f"https://doi.org/{doi}"
    )


def url_valide(
    url: Any,
) -> bool:
    if not url:
        return False

    return str(url).strip().startswith(
        (
            "http://",
            "https://",
        )
    )


def premier_element(
    valeur: Any,
) -> Optional[str]:
    if isinstance(
        valeur,
        list,
    ):
        if not valeur:
            return None

        valeur = valeur[0]

    if valeur is None:
        return None

    texte = nettoyer_texte(
        valeur
    )

    return texte or None


def liste_texte(
    valeur: Any,
) -> List[str]:
    if valeur is None:
        return []

    if not isinstance(
        valeur,
        list,
    ):
        valeur = [valeur]

    resultat = []

    for item in valeur:
        if isinstance(
            item,
            dict,
        ):
            for cle in (
                "display_name",
                "name",
                "full_name",
            ):
                if item.get(cle):
                    texte = nettoyer_texte(
                        item[cle]
                    )

                    if texte:
                        resultat.append(
                            texte
                        )

                    break

        else:
            texte = nettoyer_texte(
                item
            )

            if texte:
                resultat.append(
                    texte
                )

    return resultat


# ============================================================
# ABSTRACT OPENALEX
# ============================================================

def reconstruire_abstract(
    inverted_index: Any,
) -> str:
    if not isinstance(
        inverted_index,
        dict,
    ):
        return ""

    mots = []

    for mot, positions in (
        inverted_index.items()
    ):
        if not isinstance(
            positions,
            list,
        ):
            continue

        for position in positions:
            try:
                mots.append(
                    (
                        int(position),
                        str(mot),
                    )
                )

            except Exception:
                continue

    mots.sort(
        key=lambda element: element[0]
    )

    return " ".join(
        mot
        for _, mot in mots
    )


# ============================================================
# CORRECTION AUTOMATIQUE
# ============================================================

VOCABULAIRE = [
    # Français
    "intelligence",
    "artificielle",
    "artificiel",
    "médecine",
    "médecin",
    "médical",
    "médicale",
    "santé",
    "technologie",
    "technologies",
    "informatique",
    "programmation",
    "programme",
    "étudiant",
    "étudiants",
    "formation",
    "performance",
    "apprentissage",
    "recherche",
    "scientifique",
    "science",
    "application",
    "applications",
    "ordinateur",
    "données",
    "analyse",
    "système",
    "systèmes",
    "réseau",
    "réseaux",
    "algorithme",
    "algorithmes",
    "automatique",
    "profond",
    "profonde",
    "neuronal",
    "neuronale",
    "diagnostic",
    "diagnostique",
    "cancer",
    "maladie",
    "maladies",
    "patient",
    "patients",
    "clinique",
    "cliniques",
    "hôpital",
    "hôpitaux",
    "général",
    "générale",

    # Anglais
    "artificial",
    "intelligence",
    "medicine",
    "medical",
    "health",
    "healthcare",
    "technology",
    "technologies",
    "computer",
    "computing",
    "programming",
    "student",
    "students",
    "training",
    "performance",
    "learning",
    "research",
    "scientific",
    "science",
    "application",
    "applications",
    "data",
    "analysis",
    "system",
    "systems",
    "network",
    "networks",
    "algorithm",
    "algorithms",
    "machine",
    "deep",
    "neural",
    "diagnosis",
    "diagnostic",
    "cancer",
    "disease",
    "diseases",
    "patient",
    "patients",
    "clinical",
    "hospital",
    "hospitals",
]


VOCABULAIRE_NORMALISE = {}

for mot in VOCABULAIRE:
    cle = normaliser_texte(
        mot
    )

    if cle:
        VOCABULAIRE_NORMALISE[
            cle
        ] = mot


def corriger_recherche(
    sujet: str,
) -> Dict[str, Any]:
    sujet = nettoyer_texte(
        sujet
    )

    if not sujet:
        return {
            "sujet_original": "",
            "sujet_corrige": "",
            "correction_effectuee": False,
            "corrections": [],
        }

    tokens = sujet.split()

    nouveaux_tokens = []
    corrections = []

    for token in tokens:
        prefixe_match = re.match(
            r"^[^\wÀ-ÿ]*",
            token,
            flags=re.UNICODE,
        )

        suffixe_match = re.search(
            r"[^\wÀ-ÿ]*$",
            token,
            flags=re.UNICODE,
        )

        prefixe = (
            prefixe_match.group(0)
            if prefixe_match
            else ""
        )

        suffixe = (
            suffixe_match.group(0)
            if suffixe_match
            else ""
        )

        debut = len(prefixe)

        fin = (
            len(token)
            - len(suffixe)
            if suffixe
            else len(token)
        )

        coeur = token[
            debut:fin
        ]

        if (
            not coeur
            or len(coeur) <= 3
            or any(
                caractere.isdigit()
                for caractere in coeur
            )
        ):
            nouveaux_tokens.append(
                token
            )
            continue

        mot_normalise = normaliser_texte(
            coeur
        )

        if (
            mot_normalise
            in VOCABULAIRE_NORMALISE
        ):
            nouveaux_tokens.append(
                token
            )
            continue

        resultat = process.extractOne(
            mot_normalise,
            VOCABULAIRE_NORMALISE.keys(),
            scorer=fuzz.ratio,
        )

        if not resultat:
            nouveaux_tokens.append(
                token
            )
            continue

        meilleur_mot = resultat[0]
        score = resultat[1]

        if score >= 92:
            remplacement = (
                VOCABULAIRE_NORMALISE[
                    meilleur_mot
                ]
            )

            nouveau_token = (
                prefixe
                + remplacement
                + suffixe
            )

            if nouveau_token != token:
                corrections.append(
                    {
                        "avant": coeur,
                        "apres": remplacement,
                    }
                )

                nouveaux_tokens.append(
                    nouveau_token
                )

                continue

        nouveaux_tokens.append(
            token
        )

    sujet_corrige = " ".join(
        nouveaux_tokens
    )

    return {
        "sujet_original": sujet,
        "sujet_corrige": sujet_corrige,
        "correction_effectuee": (
            sujet_corrige != sujet
        ),
        "corrections": corrections,
    }


# ============================================================
# TYPES DE DOCUMENTS
# ============================================================

def normaliser_type_openalex(
    valeur: Any,
) -> str:
    texte = normaliser_texte(
        valeur
    )

    if not texte:
        return "other"

    if (
        "proceedings" in texte
        or "conference" in texte
    ):
        return "conference"

    if (
        "dissertation" in texte
        or "thesis" in texte
    ):
        return "thesis"

    if (
        "book" in texte
        or "chapter" in texte
    ):
        return "book"

    if (
        "article" in texte
        or texte in {
            "review",
            "editorial",
            "letter",
            "erratum",
        }
    ):
        return "article"

    return "other"


def normaliser_type_hal(
    valeur: Any,
) -> str:
    texte = normaliser_texte(
        valeur
    )

    if not texte:
        return "other"

    if texte in {
        "these",
        "hdr",
        "mem",
        "memoire",
        "habilitation",
    }:
        return "thesis"

    if (
        texte.startswith("comm")
        or "conference" in texte
        or "congres" in texte
    ):
        return "conference"

    if texte in {
        "ouv",
        "chap",
        "chapo",
        "ouvrage",
        "book",
        "bookchapter",
    }:
        return "book"

    if (
        texte.startswith("art")
        or "article" in texte
    ):
        return "article"

    return "other"


def normaliser_type_crossref(
    valeur: Any,
) -> str:
    texte = normaliser_texte(
        valeur
    )

    if not texte:
        return "other"

    if (
        "proceedings" in texte
        or "conference" in texte
    ):
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
    type_document = normaliser_texte(
        type_document
    )

    if type_document in {
        "",
        "all",
        "tous",
    }:
        return documents

    types_valides = {
        "article",
        "thesis",
        "conference",
        "book",
        "other",
    }

    if type_document not in types_valides:
        return documents

    return [
        document
        for document in documents
        if document.get(
            "type_document"
        ) == type_document
    ]


# ============================================================
# OPENALEX
# ============================================================

def rechercher_openalex(
    sujet: str,
) -> List[Dict[str, Any]]:
    documents = []

    for page in range(
        1,
        MAX_PAGES + 1,
    ):
        params = {
            "search": sujet,
            "page": page,
            "per-page": PER_PAGE,
        }

        try:
            response = requests.get(
                OPENALEX_URL,
                params=params,
                headers={
                    "User-Agent": USER_AGENT
                },
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 429:
                time.sleep(2)
                continue

            if response.status_code != 200:
                break

            data = response.json()

        except Exception:
            break

        results = data.get(
            "results",
            [],
        )

        if not results:
            break

        for work in results:
            titre = nettoyer_texte(
                work.get(
                    "display_name"
                )
                or work.get(
                    "title"
                )
            )

            if not titre:
                continue

            annee = extraire_annee(
                work.get(
                    "publication_year"
                )
            )

            doi = normaliser_doi(
                work.get(
                    "doi"
                )
            )

            oa = (
                work.get(
                    "open_access"
                )
                or {}
            )

            open_access = bool(
                oa.get(
                    "is_oa"
                )
            )

            oa_status = (
                oa.get(
                    "oa_status"
                )
                or None
            )

            pdf_url = None

            best_location = (
                work.get(
                    "best_oa_location"
                )
                or {}
            )

            if best_location:
                pdf_url = (
                    best_location.get(
                        "pdf_url"
                    )
                )

            if not pdf_url:
                locations = (
                    work.get(
                        "locations"
                    )
                    or []
                )

                for location in locations:
                    if not isinstance(
                        location,
                        dict,
                    ):
                        continue

                    candidate = (
                        location.get(
                            "pdf_url"
                        )
                    )

                    if candidate:
                        pdf_url = candidate
                        break

            abstract = reconstruire_abstract(
                work.get(
                    "abstract_inverted_index"
                )
            )

            auteurs = []

            for authorship in (
                work.get(
                    "authorships"
                )
                or []
            ):
                if not isinstance(
                    authorship,
                    dict,
                ):
                    continue

                author = (
                    authorship.get(
                        "author"
                    )
                    or {}
                )

                nom = nettoyer_texte(
                    author.get(
                        "display_name"
                    )
                )

                if nom:
                    auteurs.append(
                        nom
                    )

            keywords = []

            for keyword in (
                work.get(
                    "keywords"
                )
                or []
            ):
                if isinstance(
                    keyword,
                    dict,
                ):
                    nom = nettoyer_texte(
                        keyword.get(
                            "display_name"
                        )
                    )

                    if nom:
                        keywords.append(
                            nom
                        )

            primary_location = (
                work.get(
                    "primary_location"
                )
                or {}
            )

            source_info = (
                primary_location.get(
                    "source"
                )
                or {}
            )

            journal = nettoyer_texte(
                source_info.get(
                    "display_name"
                )
            ) or None

            document = {
                "titre": titre,
                "annee": annee,
                "doi": doi,
                "source": "OpenAlex",

                "open_access": open_access,

                "oa_status": oa_status,
                "statut_oa": oa_status,

                "lien_pdf": pdf_url,

                # IMPORTANT :
                # pas de vérification HTTP ici.
                # Cela accélère fortement la recherche.
                "pdf_valide": bool(
                    pdf_url
                ),

                "score": 0,

                "resume": abstract,
                "abstract": abstract,

                "auteurs": auteurs,

                "journal": journal,

                "url": (
                    url_doi(doi)
                    or work.get(
                        "id"
                    )
                ),

                "keywords": keywords,

                "type_document": (
                    normaliser_type_openalex(
                        work.get(
                            "type"
                        )
                    )
                ),
            }

            documents.append(
                document
            )

            if len(documents) >= MAX_SOURCE_RESULTS:
                return documents

    return documents


# ============================================================
# HAL
# ============================================================

def rechercher_hal(
    sujet: str,
) -> List[Dict[str, Any]]:
    documents = []

    for page in range(
        MAX_PAGES
    ):
        start = (
            page * PER_PAGE
        )

        params = {
            "q": sujet,
            "rows": PER_PAGE,
            "start": start,
            "wt": "json",

            "fl": (
                "title_s,"
                "title_t,"
                "producedDateY_i,"
                "doiId_s,"
                "uri_s,"
                "fileMain_s,"
                "abstract_s,"
                "keyword_s,"
                "authFullName_s,"
                "journalTitle_s,"
                "docType_s"
            ),
        }

        try:
            response = requests.get(
                HAL_URL,
                params=params,
                headers={
                    "User-Agent": USER_AGENT
                },
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 429:
                time.sleep(2)
                continue

            if response.status_code != 200:
                break

            data = response.json()

        except Exception:
            break

        response_data = data.get(
            "response",
            {},
        )

        docs = response_data.get(
            "docs",
            [],
        )

        if not docs:
            break

        for item in docs:
            titre = (
                premier_element(
                    item.get(
                        "title_s"
                    )
                )
                or premier_element(
                    item.get(
                        "title_t"
                    )
                )
            )

            if not titre:
                continue

            annee = extraire_annee(
                item.get(
                    "producedDateY_i"
                )
            )

            doi = normaliser_doi(
                item.get(
                    "doiId_s"
                )
            )

            uri = premier_element(
                item.get(
                    "uri_s"
                )
            )

            file_url = premier_element(
                item.get(
                    "fileMain_s"
                )
            )

            if (
                file_url
                and not url_valide(
                    file_url
                )
            ):
                file_url = None

            abstract = (
                premier_element(
                    item.get(
                        "abstract_s"
                    )
                )
                or ""
            )

            auteurs = liste_texte(
                item.get(
                    "authFullName_s"
                )
            )

            keywords = liste_texte(
                item.get(
                    "keyword_s"
                )
            )

            journal = (
                premier_element(
                    item.get(
                        "journalTitle_s"
                    )
                )
            )

            type_document = (
                normaliser_type_hal(
                    item.get(
                        "docType_s"
                    )
                )
            )

            open_access = bool(
                file_url
                or uri
            )

            document = {
                "titre": titre,
                "annee": annee,
                "doi": doi,
                "source": "HAL",

                "open_access": open_access,

                "oa_status": "repository",
                "statut_oa": "repository",

                "lien_pdf": (
                    file_url
                    or uri
                ),

                # On ne vérifie pas le PDF ici.
                "pdf_valide": bool(
                    file_url
                ),

                "score": 0,

                "resume": abstract,
                "abstract": abstract,

                "auteurs": auteurs,

                "journal": journal,

                "url": (
                    url_doi(doi)
                    or uri
                ),

                "keywords": keywords,

                "type_document": type_document,
            }

            documents.append(
                document
            )

            if len(documents) >= MAX_SOURCE_RESULTS:
                return documents

    return documents


# ============================================================
# CROSSREF
# ============================================================

def rechercher_crossref(
    sujet: str,
) -> List[Dict[str, Any]]:
    documents = []

    for page in range(
        MAX_PAGES
    ):
        offset = (
            page * PER_PAGE
        )

        params = {
            "query.bibliographic": sujet,
            "rows": PER_PAGE,
            "offset": offset,
        }

        try:
            response = requests.get(
                CROSSREF_URL,
                params=params,
                headers={
                    "User-Agent": USER_AGENT
                },
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 429:
                time.sleep(2)
                continue

            if response.status_code != 200:
                break

            data = response.json()

        except Exception:
            break

        message = data.get(
            "message",
            {},
        )

        items = message.get(
            "items",
            [],
        )

        if not items:
            break

        for item in items:
            titres = (
                item.get(
                    "title"
                )
                or []
            )

            titre = (
                nettoyer_texte(
                    titres[0]
                )
                if titres
                else ""
            )

            if not titre:
                continue

            doi = normaliser_doi(
                item.get(
                    "DOI"
                )
            )

            date_source = (
                item.get(
                    "published-print"
                )
                or item.get(
                    "published-online"
                )
                or item.get(
                    "issued"
                )
                or {}
            )

            date_parts = (
                date_source.get(
                    "date-parts"
                )
                or []
            )

            annee = None

            if date_parts:
                try:
                    annee = extraire_annee(
                        date_parts[0][0]
                    )
                except Exception:
                    annee = None

            pdf_url = None

            article_url = item.get(
                "URL"
            )

            links = (
                item.get(
                    "link"
                )
                or []
            )

            for link in links:
                if not isinstance(
                    link,
                    dict,
                ):
                    continue

                candidate = link.get(
                    "URL"
                )

                content_type = (
                    normaliser_texte(
                        link.get(
                            "content-type"
                        )
                    )
                )

                if (
                    candidate
                    and (
                        "application/pdf"
                        in content_type
                        or str(candidate)
                        .lower()
                        .split("?")[0]
                        .endswith(
                            ".pdf"
                        )
                    )
                ):
                    pdf_url = candidate
                    break

            abstract = nettoyer_texte(
                item.get(
                    "abstract"
                )
            )

            auteurs = []

            for author in (
                item.get(
                    "author"
                )
                or []
            ):
                if not isinstance(
                    author,
                    dict,
                ):
                    continue

                nom = nettoyer_texte(
                    (
                        author.get(
                            "given"
                        )
                        or ""
                    )
                    + " "
                    + (
                        author.get(
                            "family"
                        )
                        or ""
                    )
                )

                if nom:
                    auteurs.append(
                        nom
                    )

            journal = None

            container_titles = (
                item.get(
                    "container-title"
                )
                or []
            )

            if container_titles:
                journal = nettoyer_texte(
                    container_titles[0]
                )

            open_access = bool(
                pdf_url
            )

            document = {
                "titre": titre,
                "annee": annee,
                "doi": doi,
                "source": "Crossref",

                "open_access": open_access,

                "oa_status": (
                    "gold"
                    if open_access
                    else "closed"
                ),

                "statut_oa": (
                    "gold"
                    if open_access
                    else "closed"
                ),

                "lien_pdf": pdf_url,

                "pdf_valide": bool(
                    pdf_url
                ),

                "score": 0,

                "resume": abstract,
                "abstract": abstract,

                "auteurs": auteurs,

                "journal": journal,

                "url": (
                    url_doi(doi)
                    or article_url
                ),

                "keywords": [],

                "type_document": (
                    normaliser_type_crossref(
                        item.get(
                            "type"
                        )
                    )
                ),
            }

            documents.append(
                document
            )

            if len(documents) >= MAX_SOURCE_RESULTS:
                return documents

    return documents


# ============================================================
# SOURCES
# ============================================================

def normaliser_sources(
    sources: Any,
) -> List[str]:
    toutes = [
        "OpenAlex",
        "HAL",
        "Crossref",
    ]

    if not sources:
        return toutes

    resultat = []

    for source in sources:
        valeur = normaliser_texte(
            source
        )

        if valeur == "openalex":
            nom = "OpenAlex"

        elif valeur == "hal":
            nom = "HAL"

        elif valeur == "crossref":
            nom = "Crossref"

        else:
            continue

        if nom not in resultat:
            resultat.append(
                nom
            )

    if not resultat:
        return toutes

    return resultat


def rechercher_source(
    source: str,
    sujet: str,
) -> List[Dict[str, Any]]:
    if source == "OpenAlex":
        return rechercher_openalex(
            sujet
        )

    if source == "HAL":
        return rechercher_hal(
            sujet
        )

    if source == "Crossref":
        return rechercher_crossref(
            sujet
        )

    return []


# ============================================================
# DÉDOUBLONNAGE
# ============================================================

def cle_document(
    document: Dict[str, Any],
) -> str:
    doi = normaliser_doi(
        document.get(
            "doi"
        )
    )

    if doi:
        return (
            "doi:"
            + normaliser_texte(
                doi
            )
        )

    titre = normaliser_texte(
        document.get(
            "titre"
        )
    )

    annee = (
        document.get(
            "annee"
        )
        or ""
    )

    return (
        "titre:"
        + titre
        + "|"
        + str(annee)
    )


def choisir_meilleur_document(
    ancien: Dict[str, Any],
    nouveau: Dict[str, Any],
) -> Dict[str, Any]:
    ancien_pdf = bool(
        ancien.get(
            "lien_pdf"
        )
    )

    nouveau_pdf = bool(
        nouveau.get(
            "lien_pdf"
        )
    )

    if (
        nouveau_pdf
        and not ancien_pdf
    ):
        return nouveau

    ancien_score = float(
        ancien.get(
            "score"
        )
        or 0
    )

    nouveau_score = float(
        nouveau.get(
            "score"
        )
        or 0
    )

    if nouveau_score > ancien_score:
        return nouveau

    return ancien


def dedoublonner(
    documents: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    uniques = {}

    for document in documents:
        cle = cle_document(
            document
        )

        if cle not in uniques:
            uniques[cle] = document

        else:
            uniques[cle] = (
                choisir_meilleur_document(
                    uniques[cle],
                    document,
                )
            )

    return list(
        uniques.values()
    )


# ============================================================
# SCORE
# ============================================================

def calculer_score(
    document: Dict[str, Any],
    sujet: str,
) -> int:
    score = 0

    requete = normaliser_texte(
        sujet
    )

    mots_recherche = [
        mot
        for mot in requete.split()
        if len(mot) > 2
    ]

    titre = normaliser_texte(
        document.get(
            "titre"
        )
    )

    resume = normaliser_texte(
        document.get(
            "resume"
        )
        or document.get(
            "abstract"
        )
    )

    keywords = normaliser_texte(
        " ".join(
            document.get(
                "keywords"
            )
            or []
        )
    )

    for mot in mots_recherche:
        if mot in titre:
            score += 8

        if mot in resume:
            score += 3

        if mot in keywords:
            score += 4

    if (
        requete
        and requete in titre
    ):
        score += 10

    if document.get(
        "lien_pdf"
    ):
        score += 3

    if document.get(
        "open_access"
    ):
        score += 3

    if document.get(
        "doi"
    ):
        score += 1

    if requete and titre:
        similarite = fuzz.token_set_ratio(
            requete,
            titre,
        )

        if similarite >= 90:
            score += 8

        elif similarite >= 80:
            score += 5

        elif similarite >= 70:
            score += 2

    return int(score)


# ============================================================
# FILTRES
# ============================================================

def filtrer_par_annee(
    documents: List[Dict[str, Any]],
    annee_min: Optional[int],
    annee_max: Optional[int],
) -> List[Dict[str, Any]]:
    resultat = []

    for document in documents:
        annee = extraire_annee(
            document.get(
                "annee"
            )
        )

        if (
            annee_min is not None
            and (
                annee is None
                or annee < annee_min
            )
        ):
            continue

        if (
            annee_max is not None
            and (
                annee is None
                or annee > annee_max
            )
        ):
            continue

        resultat.append(
            document
        )

    return resultat


def filtrer_open_access(
    documents: List[Dict[str, Any]],
    open_access_only: bool,
) -> List[Dict[str, Any]]:
    if not open_access_only:
        return documents

    return [
        document
        for document in documents
        if document.get(
            "open_access"
        )
        and document.get(
            "lien_pdf"
        )
    ]


# ============================================================
# RECHERCHE PRINCIPALE
# ============================================================

@app.post("/search")
def search(
    request: SearchRequest,
):
    debut = time.time()

    sujet_original = nettoyer_texte(
        request.sujet
    )

    if not sujet_original:
        raise HTTPException(
            status_code=400,
            detail=(
                "Le sujet de recherche "
                "est obligatoire."
            ),
        )

    if (
        request.annee_min is not None
        and request.annee_max is not None
        and request.annee_min
        > request.annee_max
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "L'année minimale doit être "
                "inférieure ou égale à "
                "l'année maximale."
            ),
        )

    # --------------------------------------------------------
    # CORRECTION
    # --------------------------------------------------------

    correction = corriger_recherche(
        sujet_original
    )

    sujet_corrige = correction[
        "sujet_corrige"
    ]

    # --------------------------------------------------------
    # SOURCES
    #
    # Par défaut :
    # OpenAlex + HAL + Crossref
    # --------------------------------------------------------

    sources = normaliser_sources(
        request.sources
    )

    tous_documents = []

    erreurs_sources = []

    # --------------------------------------------------------
    # RECHERCHE PARALLÈLE
    # --------------------------------------------------------

    with ThreadPoolExecutor(
        max_workers=len(sources)
    ) as executor:

        futures = {
            executor.submit(
                rechercher_source,
                source,
                sujet_corrige,
            ): source
            for source in sources
        }

        for future in as_completed(
            futures
        ):
            source = futures[
                future
            ]

            try:
                resultats = future.result()

                tous_documents.extend(
                    resultats
                )

            except Exception as erreur:
                erreurs_sources.append(
                    {
                        "source": source,
                        "erreur": str(erreur),
                    }
                )

    # --------------------------------------------------------
    # DÉDOUBLONNAGE
    # --------------------------------------------------------

    documents = dedoublonner(
        tous_documents
    )

    nombre_avant_filtres = len(
        documents
    )

    # --------------------------------------------------------
    # FILTRE ANNÉE
    # --------------------------------------------------------

    documents = filtrer_par_annee(
        documents,
        request.annee_min,
        request.annee_max,
    )

    # --------------------------------------------------------
    # FILTRE TYPE
    # --------------------------------------------------------

    documents = filtrer_par_type(
        documents,
        request.type_document,
    )

    # --------------------------------------------------------
    # FILTRE OPEN ACCESS
    # --------------------------------------------------------

    documents = filtrer_open_access(
        documents,
        request.open_access_only,
    )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    for document in documents:
        document[
            "score"
        ] = calculer_score(
            document,
            sujet_corrige,
        )

    # --------------------------------------------------------
    # CLASSEMENT
    # --------------------------------------------------------

    documents.sort(
        key=lambda document: (
            document.get(
                "score"
            )
            or 0,

            bool(
                document.get(
                    "open_access"
                )
            ),

            bool(
                document.get(
                    "lien_pdf"
                )
            ),

            document.get(
                "annee"
            )
            or 0,
        ),
        reverse=True,
    )

    # --------------------------------------------------------
    # NOMBRE DEMANDÉ
    # --------------------------------------------------------

    documents = documents[
        : request.nombre
    ]

    # --------------------------------------------------------
    # NORMALISATION DES CHAMPS
    # --------------------------------------------------------

    for document in documents:
        document.setdefault(
            "resume",
            document.get(
                "abstract"
            )
            or "",
        )

        document.setdefault(
            "abstract",
            document.get(
                "resume"
            )
            or "",
        )

        document.setdefault(
            "oa_status",
            document.get(
                "statut_oa"
            ),
        )

        document.setdefault(
            "statut_oa",
            document.get(
                "oa_status"
            ),
        )

        document.setdefault(
            "auteurs",
            [],
        )

        document.setdefault(
            "keywords",
            [],
        )

        document.setdefault(
            "type_document",
            "other",
        )

        document.setdefault(
            "pdf_valide",
            bool(
                document.get(
                    "lien_pdf"
                )
            ),
        )

    temps_recherche = round(
        time.time() - debut,
        2,
    )

    # --------------------------------------------------------
    # RÉPONSE
    # --------------------------------------------------------

    return {
        "version": APP_VERSION,

        "sujet_original": (
            correction[
                "sujet_original"
            ]
        ),

        "sujet_corrige": (
            sujet_corrige
        ),

        "correction_effectuee": (
            correction[
                "correction_effectuee"
            ]
        ),

        "corrections": (
            correction[
                "corrections"
            ]
        ),

        "nombre_demande": (
            request.nombre
        ),

        "nombre_trouve": len(
            documents
        ),

        "nombre_avant_filtres": (
            nombre_avant_filtres
        ),

        "sources_utilisees": sources,

        "erreurs_sources": (
            erreurs_sources
        ),

        "temps_recherche": (
            temps_recherche
        ),

        "filtres": {
            "annee_min": (
                request.annee_min
            ),
            "annee_max": (
                request.annee_max
            ),
            "type_document": (
                request.type_document
            ),
            "open_access_only": (
                request.open_access_only
            ),
        },

        "documents": documents,
    }


# ============================================================
# ENDPOINTS DE BASE
# ============================================================

@app.get("/")
def root():
    return {
        "application": (
            "Scientific Document Finder"
        ),
        "version": APP_VERSION,
        "status": "online",
        "sources": [
            "OpenAlex",
            "HAL",
            "Crossref",
        ],
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
    }


# ============================================================
# TÉLÉCHARGEMENT ZIP
# ============================================================

def verifier_pdf(
    url: Any,
) -> bool:
    """
    Vérification réelle du PDF.

    Cette fonction n'est PAS utilisée pendant
    la recherche afin de conserver la rapidité.

    Elle est utilisée uniquement lors du ZIP.
    """

    if not url_valide(url):
        return False

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "application/pdf,"
            "application/octet-stream,"
            "*/*"
        ),
    }

    try:
        response = requests.get(
            str(url),
            headers=headers,
            timeout=PDF_TIMEOUT,
            stream=True,
            allow_redirects=True,
        )

        if response.status_code != 200:
            response.close()
            return False

        content_type = (
            response.headers.get(
                "content-type",
                "",
            )
            .lower()
        )

        debut = response.raw.read(
            5,
            decode_content=True,
        )

        response.close()

        if "application/pdf" in content_type:
            return True

        return debut.startswith(
            b"%PDF"
        )

    except Exception:
        return False


def nom_fichier_securise(
    titre: Any,
    annee: Any = None,
) -> str:
    titre = nettoyer_texte(
        titre
    )

    if not titre:
        titre = "document"

    titre = re.sub(
        r'[<>:"/\\|?*]+',
        "_",
        titre,
    )

    titre = re.sub(
        r"\s+",
        " ",
        titre,
    ).strip()

    titre = titre[:140]

    if annee:
        return (
            f"{annee} - {titre}.pdf"
        )

    return (
        f"{titre}.pdf"
    )


def mettre_a_jour_job(
    job_id: str,
    **valeurs: Any,
):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(
                valeurs
            )


def etat_job_compatible(
    job: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "job_id": job.get(
            "job_id"
        ),

        "status": job.get(
            "status"
        ),

        "statut": job.get(
            "statut"
        ),

        "message": job.get(
            "message"
        ),

        "etape": job.get(
            "etape"
        ),

        "percent": job.get(
            "percent",
            0,
        ),

        "pourcentage": job.get(
            "pourcentage",
            0,
        ),

        "completed": job.get(
            "completed",
            0,
        ),

        "documents_traites": job.get(
            "documents_traites",
            0,
        ),

        "total": job.get(
            "total",
            0,
        ),

        "total_documents": job.get(
            "total_documents",
            0,
        ),

        "download_ready": job.get(
            "download_ready",
            False,
        ),

        "termine": job.get(
            "termine",
            False,
        ),

        "annule": job.get(
            "annule",
            False,
        ),

        "paused": job.get(
            "paused",
            False,
        ),

        "erreur": job.get(
            "erreur"
        ),
    }


# ============================================================
# WORKER ZIP
# ============================================================

def executer_telechargement_zip(
    job_id: str,
    documents: List[
        Dict[str, Any]
    ],
):
    """Télécharge les PDF sélectionnés et construit le ZIP.

    Important : un ZIP vide n'est jamais considéré comme un succès.
    Si aucun PDF n'a pu être téléchargé, le job passe en erreur et
    le frontend reçoit un message explicite.
    """
    zip_buffer = io.BytesIO()
    total = len(documents)
    telecharges = 0
    echecs = 0
    erreurs_detaillees = []

    try:
        mettre_a_jour_job(
            job_id,
            status="running",
            statut="en_cours",
            etape="Préparation du téléchargement",
            message="Préparation du téléchargement...",
            telecharges=0,
            pdf_telecharges=0,
            echecs=0,
            pdf_echecs=0,
        )

        noms_utilises = set()

        with zipfile.ZipFile(
            zip_buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for index, document in enumerate(documents, start=1):
                # --------------------------------------------
                # PAUSE / ANNULATION
                # --------------------------------------------
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
                titre = document.get("titre") or "document"
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
                    raison_echec = "Aucun lien PDF disponible."
                elif not verifier_pdf(pdf_url):
                    raison_echec = "Le lien PDF n'est pas accessible ou ne retourne pas un PDF valide."
                else:
                    try:
                        response = requests.get(
                            str(pdf_url),
                            headers={
                                "User-Agent": USER_AGENT,
                                "Accept": "application/pdf,*/*",
                            },
                            timeout=PDF_TIMEOUT,
                            allow_redirects=True,
                        )

                        if response.status_code != 200:
                            raison_echec = (
                                f"Le serveur PDF a retourné HTTP {response.status_code}."
                            )
                        else:
                            contenu = response.content

                            if not contenu.startswith(b"%PDF"):
                                raison_echec = "Le fichier reçu n'est pas un PDF valide."
                            else:
                                nom = nom_fichier_securise(titre, annee)
                                base_nom = nom
                                compteur = 2

                                while nom in noms_utilises:
                                    if nom.lower().endswith(".pdf"):
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
                                telecharges += 1

                        response.close()

                    except requests.RequestException as erreur:
                        raison_echec = f"Erreur réseau : {erreur}"
                    except Exception as erreur:
                        raison_echec = f"Erreur : {erreur}"

                if raison_echec:
                    echecs += 1
                    erreurs_detaillees.append(
                        f"{titre} — {raison_echec}"
                    )

                pourcentage = int(index / total * 100) if total else 100

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

        # ----------------------------------------------------
        # FIN : empêcher les ZIP vides
        # ----------------------------------------------------
        if telecharges == 0:
            message = (
                f"Aucun PDF n'a pu être téléchargé sur {total} document(s). "
                "Le ZIP vide n'a pas été créé. Vérifiez les liens PDF ou "
                "activez le filtre « PDF disponible uniquement »."
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

        zip_data = zip_buffer.getvalue()

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

            jobs[job_id]["zip_data"] = zip_data
            jobs[job_id].update(
                {
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
                }
            )

    except Exception as erreur:
        mettre_a_jour_job(
            job_id,
            status="error",
            statut="erreur",
            message="Une erreur est survenue pendant la création du ZIP.",
            etape="Erreur",
            erreur=str(erreur),
            termine=False,
            download_ready=False,
        )


# ============================================================
# POST /download-zip
# ============================================================

@app.post("/download-zip")
def download_zip(
    request: DownloadZipRequest,
):
    documents = request.documents

    if not documents:
        raise HTTPException(
            status_code=400,
            detail=(
                "Aucun document à télécharger."
            ),
        )

    job_id = str(
        uuid.uuid4()
    )

    cancel_event = threading.Event()

    jobs[job_id] = {
        "job_id": job_id,

        "status": "starting",
        "statut": "demarrage",

        "message": (
            "Démarrage du téléchargement..."
        ),

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
        args=(
            job_id,
            documents,
        ),
        daemon=True,
    )

    thread.start()

    return {
        "job_id": job_id,
        "status": "starting",
        "statut": "demarrage",
        "message": (
            "Téléchargement démarré."
        ),
    }


# ============================================================
# GET /download-progress/{job_id}
# ============================================================

@app.get(
    "/download-progress/{job_id}"
)
def download_progress(
    job_id: str,
):
    with jobs_lock:
        job = jobs.get(
            job_id
        )

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job introuvable.",
            )

        return etat_job_compatible(
            job
        )


# ============================================================
# GET /download-zip/{job_id}
# ============================================================

@app.get(
    "/download-zip/{job_id}"
)
def get_download_zip(
    job_id: str,
):
    limite = time.time() + 120

    while time.time() < limite:

        with jobs_lock:
            job = jobs.get(
                job_id
            )

            if not job:
                raise HTTPException(
                    status_code=404,
                    detail="Job introuvable.",
                )

            zip_data = job.get(
                "zip_data"
            )

            if zip_data is not None:
                break

            if job.get(
                "status"
            ) in {
                "cancelled",
                "error",
            }:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        job.get(
                            "message"
                        )
                        or (
                            "Le téléchargement "
                            "n'est pas disponible."
                        )
                    ),
                )

        time.sleep(
            0.25
        )

    else:
        raise HTTPException(
            status_code=409,
            detail=(
                "Le fichier ZIP "
                "n'est pas encore prêt."
            ),
        )

    return Response(
        content=zip_data,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                'attachment; '
                'filename="'
                'scientific_documents.zip'
                '"'
            )
        },
    )


# ============================================================
# POST /download-pause/{job_id}
# ============================================================

@app.post(
    "/download-pause/{job_id}"
)
def pause_download(
    job_id: str,
):
    with jobs_lock:
        job = jobs.get(
            job_id
        )

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job introuvable.",
            )

        if job.get(
            "termine"
        ):
            return etat_job_compatible(
                job
            )

        if job.get(
            "annule"
        ):
            return etat_job_compatible(
                job
            )

        job[
            "paused"
        ] = True

        job[
            "status"
        ] = "paused"

        job[
            "statut"
        ] = "en_pause"

        job[
            "message"
        ] = "Téléchargement en pause."

        job[
            "etape"
        ] = "En pause"

        return etat_job_compatible(
            job
        )


# ============================================================
# POST /download-resume/{job_id}
# ============================================================

@app.post(
    "/download-resume/{job_id}"
)
def resume_download(
    job_id: str,
):
    with jobs_lock:
        job = jobs.get(
            job_id
        )

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job introuvable.",
            )

        if job.get(
            "termine"
        ):
            return etat_job_compatible(
                job
            )

        if job.get(
            "annule"
        ):
            return etat_job_compatible(
                job
            )

        job[
            "paused"
        ] = False

        job[
            "status"
        ] = "running"

        job[
            "statut"
        ] = "en_cours"

        job[
            "message"
        ] = "Téléchargement repris."

        return etat_job_compatible(
            job
        )


# ============================================================
# POST /download-cancel/{job_id}
# ============================================================

@app.post(
    "/download-cancel/{job_id}"
)
def cancel_download(
    job_id: str,
):
    with jobs_lock:
        job = jobs.get(
            job_id
        )

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job introuvable.",
            )

        cancel_event = job.get(
            "cancel_event"
        )

        if cancel_event:
            cancel_event.set()

        job[
            "paused"
        ] = False

        job[
            "status"
        ] = "cancelled"

        job[
            "statut"
        ] = "annule"

        job[
            "message"
        ] = "Annulation demandée."

        job[
            "etape"
        ] = "Annulation"

        job[
            "annule"
        ] = True

        return etat_job_compatible(
            job
        )


# ============================================================
# FIN
# ============================================================