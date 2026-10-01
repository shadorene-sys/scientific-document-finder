"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API_URL = "http://127.0.0.1:8000";

type DocumentScientifique = {
  id?: string | number;
  titre: string;
  annee?: number | null;
  doi?: string | null;
  source?: string | null;
  open_access?: boolean;
  oa_status?: string | null;
  statut_oa?: string | null;
  lien_pdf?: string | null;
  pdf_valide?: boolean;
  score?: number;
  resume?: string | null;
  abstract?: string | null;
  auteurs?: string[];
  journal?: string | null;
  type_document?: string | null;
  url?: string | null;
};

type CorrectionRecherche = {
  originale?: string;
  corrigee?: string;
  correction?: string;
  message?: string;
};

type ResultatRecherche = {
  documents?: DocumentScientifique[];
  resultats?: DocumentScientifique[];
  correction?: CorrectionRecherche | null;
  recherche_corrigee?: string | null;
  message?: string;
  detail?: string;
  total?: number;
};

type ProgressionTelechargement = {
  id?: string;
  job_id?: string;

  status?: string;
  statut?: string;

  progress?: number;
  progression?: number;
  percent?: number;
  pourcentage?: number;

  total?: number;
  total_documents?: number;

  completed?: number;
  documents_traites?: number;

  telecharges?: number;
  pdf_telecharges?: number;

  echecs?: number;
  pdf_echecs?: number;

  message?: string;
  etape?: string;

  download_ready?: boolean;
  termine?: boolean;
  annule?: boolean;
  paused?: boolean;

  erreur?: string | null;

  erreurs_detaillees?: string[];
};

const SOURCES = ["OpenAlex", "HAL", "Crossref"];

function BookOpenIcon() {
  return (
    <svg
      width="21"
      height="21"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M2.5 5.5A2.5 2.5 0 0 1 5 3h5a2 2 0 0 1 2 2v16a2 2 0 0 0-2-2H5a2.5 2.5 0 0 0-2.5 2.5z" />
      <path d="M21.5 5.5A2.5 2.5 0 0 0 19 3h-5a2 2 0 0 0-2 2v16a2 2 0 0 1 2-2h5a2.5 2.5 0 0 1 2.5 2.5z" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg
      width="19"
      height="19"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function FilterIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 6h16" />
      <path d="M7 12h10" />
      <path d="M10 18h4" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 21h14" />
    </svg>
  );
}

function ExternalIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M14 5h5v5" />
      <path d="M10 14 19 5" />
      <path d="M19 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m5 12 4 4L19 6" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="currentColor"
    >
      <rect x="6" y="4" width="4" height="16" rx="1" />
      <rect x="14" y="4" width="4" height="16" rx="1" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="currentColor"
    >
      <path d="M8 5v14l11-7z" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    >
      <path d="M6 6l12 12" />
      <path d="M18 6 6 18" />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function libelleTypeDocument(type?: string | null) {
  switch ((type || "").toLowerCase()) {
    case "article":
      return "Article";
    case "thesis":
      return "Mémoire / Thèse";
    case "conference":
      return "Conférence";
    case "book":
      return "Livre";
    case "other":
      return "Autre";
    default:
      return "";
  }
}

function cleDocument(
  document: DocumentScientifique,
  index: number
) {
  return (
    document.doi ||
    document.id ||
    `${document.titre}-${document.annee || "sans-annee"}-${index}`
  );
}

export default function Home() {
  const [sujet, setSujet] = useState("");

  const [nombreDocuments, setNombreDocuments] = useState(10);
  const [anneeMin, setAnneeMin] = useState(2020);
  const [anneeMax, setAnneeMax] = useState(2026);

  const [openAccessSeulement, setOpenAccessSeulement] =
    useState(false);

  const [pdfSeulement, setPdfSeulement] = useState(false);

  const [typeDocument, setTypeDocument] = useState("all");

  const [sourcesSelectionnees, setSourcesSelectionnees] =
    useState<string[]>([]);

  const [documents, setDocuments] = useState<
    DocumentScientifique[]
  >([]);

  const [correction, setCorrection] =
    useState<CorrectionRecherche | null>(null);

  const [rechercheEffectuee, setRechercheEffectuee] =
    useState(false);

  const [chargement, setChargement] = useState(false);

  const [erreur, setErreur] = useState("");

  const [filtreOuvert, setFiltreOuvert] = useState(false);

  const [documentsSelectionnes, setDocumentsSelectionnes] =
    useState<(string | number)[]>([]);

  const [jobId, setJobId] = useState<string | null>(null);

  const [progression, setProgression] =
    useState<ProgressionTelechargement | null>(null);

  const [telechargementActif, setTelechargementActif] =
    useState(false);

  const [telechargementTermine, setTelechargementTermine] =
    useState(false);

  const [telechargementAnnule, setTelechargementAnnule] =
    useState(false);

  const [page, setPage] = useState(1);

  const documentsParPage = 10;

  /*
   * Empêche de déclencher plusieurs fois
   * le téléchargement automatique du ZIP.
   */
  const zipTelechargeRef = useRef(false);

  const documentsFiltres = useMemo(() => {
    return documents.filter((document) => {
      const annee = document.annee;

      if (
        annee !== null &&
        annee !== undefined &&
        (annee < anneeMin || annee > anneeMax)
      ) {
        return false;
      }

      if (
        openAccessSeulement &&
        !document.open_access
      ) {
        return false;
      }

      if (
        pdfSeulement &&
        !document.lien_pdf
      ) {
        return false;
      }

      if (
        sourcesSelectionnees.length > 0 &&
        !sourcesSelectionnees.includes(
          document.source || ""
        )
      ) {
        return false;
      }

      if (
        typeDocument !== "all" &&
        (document.type_document || "other") !==
          typeDocument
      ) {
        return false;
      }

      return true;
    });
  }, [
    documents,
    anneeMin,
    anneeMax,
    openAccessSeulement,
    pdfSeulement,
    sourcesSelectionnees,
    typeDocument,
  ]);

  const totalPages = Math.max(
    1,
    Math.ceil(
      documentsFiltres.length /
        documentsParPage
    )
  );

  const documentsAffiches =
    documentsFiltres.slice(
      (page - 1) * documentsParPage,
      page * documentsParPage
    );

  const nombreFiltresActifs =
    Number(anneeMin !== 2020) +
    Number(anneeMax !== 2026) +
    Number(openAccessSeulement) +
    Number(pdfSeulement) +
    Number(typeDocument !== "all") +
    Number(nombreDocuments !== 10) +
    Number(sourcesSelectionnees.length > 0);

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  useEffect(() => {
    setDocumentsSelectionnes([]);
  }, [
    anneeMin,
    anneeMax,
    openAccessSeulement,
    pdfSeulement,
    typeDocument,
    sourcesSelectionnees,
  ]);

  /*
   * ========================================================
   * POLLING DE LA PROGRESSION
   * ========================================================
   *
   * Le frontend demande régulièrement au backend :
   *
   * GET /download-progress/{job_id}
   *
   * Le backend renvoie :
   *
   * 0 / 50
   * 1 / 50
   * 2 / 50
   * ...
   * 50 / 50
   */
  useEffect(() => {
    if (
      !jobId ||
      !telechargementActif
    ) {
      return;
    }

    let actif = true;

    const verifierProgression =
      async () => {
        try {
          const response =
            await fetch(
              `${API_URL}/download-progress/${jobId}`,
              {
                cache: "no-store",
              }
            );

          if (!response.ok) {
            return;
          }

          const data: ProgressionTelechargement =
            await response.json();

          if (!actif) {
            return;
          }

          setProgression(data);

          const statut = (
            data.status ||
            data.statut ||
            ""
          ).toLowerCase();

          /*
           * -----------------------------------------------
           * ANNULATION
           * -----------------------------------------------
           */
          if (
            statut === "cancelled" ||
            statut === "canceled" ||
            statut === "annule" ||
            statut === "annulé"
          ) {
            setTelechargementActif(false);
            setTelechargementTermine(false);
            setTelechargementAnnule(true);
            return;
          }

          /*
           * -----------------------------------------------
           * ERREUR
           * -----------------------------------------------
           */
          if (
            statut === "error" ||
            statut === "failed" ||
            statut === "erreur"
          ) {
            setTelechargementActif(false);
            setTelechargementTermine(false);

            setErreur(
              data.message ||
                data.erreur ||
                "Le téléchargement a échoué."
            );

            return;
          }

          /*
           * -----------------------------------------------
           * SUCCÈS
           * -----------------------------------------------
           *
           * On attend download_ready=true envoyé
           * par ton backend.
           */
          const pourcentage =
            Number(
              data.percent ??
                data.pourcentage ??
                data.progress ??
                data.progression ??
                0
            );

          const termine =
            data.download_ready === true ||
            data.termine === true ||
            statut === "completed" ||
            statut === "complete" ||
            statut === "finished" ||
            statut === "termine" ||
            statut === "terminé" ||
            pourcentage >= 100;

          if (termine) {
            setTelechargementActif(false);
            setTelechargementTermine(true);

            /*
             * Le backend indique que le ZIP est prêt.
             * On déclenche automatiquement le téléchargement.
             */
            if (
              data.download_ready === true &&
              !zipTelechargeRef.current
            ) {
              zipTelechargeRef.current = true;

              try {
                await recupererZipPourJob(
                  jobId
                );
              } catch (error) {
                if (!actif) {
                  return;
                }

                setErreur(
                  error instanceof Error
                    ? error.message
                    : "Impossible de récupérer le ZIP."
                );
              }
            }
          }
        } catch {
          /*
           * On ne coupe pas le téléchargement
           * si une requête de polling échoue.
           *
           * Le prochain polling réessaiera.
           */
        }
      };

    verifierProgression();

    const interval =
      setInterval(
        verifierProgression,
        700
      );

    return () => {
      actif = false;
      clearInterval(interval);
    };
  }, [
    jobId,
    telechargementActif,
  ]);

  async function rechercher(
    rechercheSujet?: string
  ) {
    const terme = (
      rechercheSujet ?? sujet
    ).trim();

    if (!terme) {
      setErreur(
        "Veuillez saisir un sujet de recherche."
      );
      return;
    }

    if (anneeMin > anneeMax) {
      setErreur(
        "L'année minimale doit être inférieure ou égale à l'année maximale."
      );
      return;
    }

    setChargement(true);
    setErreur("");
    setRechercheEffectuee(true);
    setDocumentsSelectionnes([]);
    setPage(1);

    try {
      const requete = {
        sujet: terme,

        nombre: nombreDocuments,

        annee_min: anneeMin,

        annee_max: anneeMax,

        sources:
          sourcesSelectionnees.length > 0
            ? sourcesSelectionnees
            : [
                "OpenAlex",
                "HAL",
                "Crossref",
              ],

        type_document:
          typeDocument,

        open_access_only:
          openAccessSeulement,
      };

      const response =
        await fetch(
          `${API_URL}/search`,
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json",
            },
            body: JSON.stringify(
              requete
            ),
          }
        );

      let data: ResultatRecherche =
        {};

      try {
        data =
          await response.json();
      } catch {
        throw new Error(
          "Le serveur a retourné une réponse qui n'est pas du JSON."
        );
      }

      if (!response.ok) {
        throw new Error(
          data.message ||
            data.detail ||
            `Erreur du serveur (${response.status}).`
        );
      }

      const nouveauxDocuments =
        data.documents ||
        data.resultats ||
        [];

      setDocuments(
        nouveauxDocuments
      );

      setCorrection(
        data.correction ||
          null
      );

      if (
        data.recherche_corrigee
      ) {
        setCorrection({
          originale: terme,
          corrigee:
            data.recherche_corrigee,
        });
      }

      if (
        nouveauxDocuments.length ===
        0
      ) {
        setErreur(
          "Aucun document ne correspond aux critères de recherche."
        );
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Une erreur est survenue pendant la recherche.";

      if (
        message.includes(
          "Failed to fetch"
        ) ||
        message.includes(
          "NetworkError"
        )
      ) {
        setErreur(
          "Impossible de contacter le backend. Vérifiez que FastAPI est lancé sur http://127.0.0.1:8000."
        );
      } else {
        setErreur(message);
      }

      setDocuments([]);
      setCorrection(null);
    } finally {
      setChargement(false);
    }
  }

  function utiliserCorrection() {
    const termeCorrige =
      correction?.corrigee ||
      correction?.correction ||
      correction?.message;

    if (!termeCorrige) {
      return;
    }

    setSujet(termeCorrige);

    rechercher(
      termeCorrige
    );
  }

  function modifierSource(
    source: string
  ) {
    setSourcesSelectionnees(
      (actuelles) => {
        if (
          actuelles.includes(
            source
          )
        ) {
          return actuelles.filter(
            (item) =>
              item !== source
          );
        }

        return [
          ...actuelles,
          source,
        ];
      }
    );

    setPage(1);
  }

  function reinitialiserFiltres() {
    setNombreDocuments(10);
    setAnneeMin(2020);
    setAnneeMax(2026);
    setOpenAccessSeulement(
      false
    );
    setPdfSeulement(false);
    setTypeDocument("all");
    setSourcesSelectionnees([]);
    setPage(1);
  }

  function modifierSelection(
    document: DocumentScientifique,
    index: number
  ) {
    const cle =
      cleDocument(
        document,
        index
      );

    setDocumentsSelectionnes(
      (actuelles) => {
        if (
          actuelles.includes(
            cle
          )
        ) {
          return actuelles.filter(
            (item) =>
              item !== cle
          );
        }

        setErreur("");

        return [
          ...actuelles,
          cle,
        ];
      }
    );
  }

  function documentEstSelectionne(
    document: DocumentScientifique,
    index: number
  ) {
    return documentsSelectionnes.includes(
      cleDocument(
        document,
        index
      )
    );
  }

  const toutesLesCles =
    documentsFiltres.map(
      (
        document,
        index
      ) =>
        cleDocument(
          document,
          index
        )
    );

  const tousLesDocumentsSelectionnes =
    toutesLesCles.length > 0 &&
    toutesLesCles.every(
      (cle) =>
        documentsSelectionnes.includes(
          cle
        )
    );

  function basculerSelectionTout() {
    if (
      documentsFiltres.length ===
      0
    ) {
      return;
    }

    setErreur("");

    if (
      tousLesDocumentsSelectionnes
    ) {
      setDocumentsSelectionnes(
        []
      );

      return;
    }

    setDocumentsSelectionnes(
      toutesLesCles
    );
  }

  /*
   * ========================================================
   * TÉLÉCHARGEMENT
   * ========================================================
   */
  async function telechargerSelection() {
    if (
      documentsSelectionnes.length ===
      0
    ) {
      setErreur(
        "Sélectionnez au moins un document."
      );

      return;
    }

    setErreur("");

    setTelechargementTermine(
      false
    );

    setTelechargementAnnule(
      false
    );

    setProgression(null);

    setJobId(null);

    /*
     * Autorise le prochain ZIP
     * à être téléchargé automatiquement.
     */
    zipTelechargeRef.current =
      false;

    const documentsAtelecharger =
      documentsFiltres.filter(
        (
          document,
          index
        ) =>
          documentsSelectionnes.includes(
            cleDocument(
              document,
              index
            )
          )
      );

    if (
      documentsAtelecharger.length ===
      0
    ) {
      setErreur(
        "Aucun document sélectionné ne possède de PDF téléchargeable."
      );

      return;
    }

    try {
      const response =
        await fetch(
          `${API_URL}/download-zip`,
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json",
            },
            body: JSON.stringify({
              documents:
                documentsAtelecharger,
            }),
          }
        );

      let data: {
        job_id?: string;
        id?: string;
        message?: string;
        detail?: string;
      } = {};

      try {
        data =
          await response.json();
      } catch {
        throw new Error(
          "Le serveur a retourné une réponse invalide."
        );
      }

      if (!response.ok) {
        throw new Error(
          data.message ||
            data.detail ||
            `Erreur lors de la préparation du téléchargement (${response.status}).`
        );
      }

      const nouveauJobId =
        data.job_id ||
        data.id;

      if (!nouveauJobId) {
        throw new Error(
          "Le serveur n'a pas retourné d'identifiant de téléchargement."
        );
      }

      setJobId(
        nouveauJobId
      );

      setTelechargementActif(
        true
      );
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Erreur pendant le téléchargement.";

      if (
        message.includes(
          "Failed to fetch"
        )
      ) {
        setErreur(
          "Impossible de contacter le backend pour le téléchargement."
        );
      } else {
        setErreur(message);
      }
    }
  }

  /*
   * ========================================================
   * PAUSE
   * ========================================================
   */
  async function mettreEnPause() {
    if (!jobId) {
      return;
    }

    try {
      const response =
        await fetch(
          `${API_URL}/download-pause/${jobId}`,
          {
            method: "POST",
          }
        );

      if (!response.ok) {
        throw new Error(
          "Le backend n'a pas pu mettre le téléchargement en pause."
        );
      }

      const data =
        await response.json();

      setProgression(
        data
      );
    } catch {
      setErreur(
        "Impossible de mettre le téléchargement en pause."
      );
    }
  }

  /*
   * ========================================================
   * REPRISE
   * ========================================================
   */
  async function reprendreTelechargement() {
    if (!jobId) {
      return;
    }

    try {
      const response =
        await fetch(
          `${API_URL}/download-resume/${jobId}`,
          {
            method: "POST",
          }
        );

      if (!response.ok) {
        throw new Error(
          "Le backend n'a pas pu reprendre le téléchargement."
        );
      }

      const data =
        await response.json();

      setProgression(
        data
      );

      setTelechargementActif(
        true
      );
    } catch {
      setErreur(
        "Impossible de reprendre le téléchargement."
      );
    }
  }

  /*
   * ========================================================
   * ANNULATION
   * ========================================================
   */
  async function annulerTelechargement() {
    if (!jobId) {
      return;
    }

    try {
      const response =
        await fetch(
          `${API_URL}/download-cancel/${jobId}`,
          {
            method: "POST",
          }
        );

      if (!response.ok) {
        throw new Error(
          "Le backend n'a pas pu annuler le téléchargement."
        );
      }

      const data =
        await response.json();

      setProgression(
        data
      );

      setTelechargementActif(
        false
      );

      setTelechargementTermine(
        false
      );

      setTelechargementAnnule(
        true
      );
    } catch {
      setErreur(
        "Impossible d'annuler le téléchargement."
      );
    }
  }

  /*
   * ========================================================
   * RÉCUPÉRATION DU ZIP
   * ========================================================
   */
  async function recupererZipPourJob(
    identifiantJob: string
  ) {
    const response =
      await fetch(
        `${API_URL}/download-zip/${identifiantJob}`,
        {
          cache: "no-store",
        }
      );

    if (!response.ok) {
      let message =
        "Le fichier ZIP n'est pas encore disponible.";

      try {
        const data =
          await response.json();

        message =
          data.message ||
          data.detail ||
          message;
      } catch {
        // Rien à faire.
      }

      throw new Error(
        message
      );
    }

    const blob =
      await response.blob();

    const url =
      window.URL.createObjectURL(
        blob
      );

    const lien =
      document.createElement(
        "a"
      );

    lien.href = url;

    lien.download =
      "scientific-documents.zip";

    document.body.appendChild(
      lien
    );

    lien.click();

    lien.remove();

    /*
     * On attend un petit moment avant
     * de supprimer l'URL temporaire.
     */
    window.setTimeout(() => {
      window.URL.revokeObjectURL(
        url
      );
    }, 1000);
  }

  async function recupererZip() {
    if (!jobId) {
      return;
    }

    try {
      await recupererZipPourJob(
        jobId
      );

      setErreur("");
    } catch (error) {
      setErreur(
        error instanceof Error
          ? error.message
          : "Impossible de récupérer le fichier ZIP."
      );
    }
  }

  /*
   * ========================================================
   * DONNÉES DE PROGRESSION
   * ========================================================
   */

  const progressionPourcentage =
    Math.min(
      100,
      Math.max(
        0,
        Number(
          progression?.percent ??
            progression?.pourcentage ??
            progression?.progress ??
            progression?.progression ??
            0
        )
      )
    );

  const documentsTraites =
    Number(
      progression?.documents_traites ??
        progression?.completed ??
        0
    );

  const totalDocuments =
    Number(
      progression?.total_documents ??
        progression?.total ??
        documentsSelectionnes.length
    );

  const pdfTelecharges =
    Number(
      progression?.pdf_telecharges ??
        progression?.telecharges ??
        0
    );

  const pdfEchecs =
    Number(
      progression?.pdf_echecs ??
        progression?.echecs ??
        0
    );

  const statutTelechargement = (
    progression?.status ||
    progression?.statut ||
    ""
  ).toLowerCase();

  const telechargementEnPause =
    progression?.paused === true ||
    statutTelechargement ===
      "paused" ||
    statutTelechargement ===
      "pause" ||
    statutTelechargement ===
      "en_pause" ||
    statutTelechargement ===
      "en pause";

  const telechargementEnErreur =
    statutTelechargement ===
      "error" ||
    statutTelechargement ===
      "failed" ||
    statutTelechargement ===
      "erreur";

  return (
    <main className="min-h-screen bg-[#020409] text-slate-100">
      {/* ==================================================
          HEADER
      ================================================== */}

      <header className="border-b border-[#10284d] bg-[#05070A]">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 lg:px-8">
          <a
            href="#recherche"
            className="flex items-center gap-3"
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600 text-white shadow-lg shadow-blue-600/20">
              <BookOpenIcon />
            </div>

            <div>
              <div className="text-base font-bold tracking-tight text-white sm:text-lg">
                Scientific Document Finder
              </div>

              <div className="hidden text-xs text-slate-500 sm:block">
                Recherche scientifique intelligente
              </div>
            </div>
          </a>

          <div className="hidden items-center gap-6 text-sm font-medium text-slate-500 md:flex">
            <a
              href="#recherche"
              className="transition hover:text-[#5da2ff]"
            >
              Recherche
            </a>

            <a
              href="#resultats"
              className="transition hover:text-[#5da2ff]"
            >
              Résultats
            </a>
          </div>
        </div>
      </header>

      {/* ==================================================
          HERO / RECHERCHE
      ================================================== */}

      <section
        id="recherche"
        className="border-b border-[#10284d] bg-[#05070A]"
      >
        <div className="mx-auto max-w-7xl px-5 py-12 lg:px-8 lg:py-16">
          <div className="mx-auto max-w-4xl text-center">
            <div className="mb-4 inline-flex items-center rounded-full bg-[#0B3D91]/20 px-4 py-2 text-sm font-medium text-[#5da2ff]">
              Recherche scientifique multi-sources
            </div>

            <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl lg:text-5xl">
              Trouvez rapidement vos documents scientifiques
            </h1>

            <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-slate-500">
              Recherchez dans OpenAlex, HAL et Crossref avec correction
              automatique, filtrage et téléchargement des documents.
            </p>

            <div className="mt-8">
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  rechercher();
                }}
                className="mx-auto flex max-w-3xl flex-col gap-3 sm:flex-row"
              >
                <div className="relative flex-1">
                  <div className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-500">
                    <SearchIcon />
                  </div>

                  <input
                    value={sujet}
                    onChange={(event) =>
                      setSujet(
                        event.target.value
                      )
                    }
                    placeholder="Ex. intelligence artificielle en médecine"
                    className="h-14 w-full rounded-2xl border border-[#29476b] bg-[#05070A] pl-12 pr-4 text-sm outline-none transition placeholder:text-slate-500 focus:border-[#1677FF] focus:ring-4 focus:ring-[#1677FF]/20"
                  />
                </div>

                <button
                  type="submit"
                  disabled={chargement}
                  className="h-14 rounded-2xl bg-blue-600 px-7 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:bg-[#0B3D91] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {chargement
                    ? "Recherche..."
                    : "Rechercher"}
                </button>
              </form>
            </div>

            {/* CORRECTION */}

            {correction &&
              (correction.corrigee ||
                correction.correction ||
                correction.message) && (
                <div className="mx-auto mt-5 flex max-w-3xl flex-col gap-3 rounded-2xl border border-amber-800 bg-amber-950/40 p-4 text-left sm:flex-row sm:items-center sm:justify-between">
                  <div className="text-sm text-amber-900">
                    <span className="font-semibold">
                      Correction proposée :
                    </span>{" "}
                    <span className="font-medium">
                      {correction.corrigee ||
                        correction.correction ||
                        correction.message}
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={
                      utiliserCorrection
                    }
                    className="shrink-0 rounded-xl bg-amber-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-700"
                  >
                    Utiliser
                  </button>
                </div>
              )}
          </div>
        </div>
      </section>

      {/* ==================================================
          CONTENU
      ================================================== */}

      <section
        id="resultats"
        className="mx-auto max-w-7xl px-5 py-8 lg:px-8"
      >
        {/* BARRE OUTILS */}

        <div className="mb-6 flex flex-col gap-4 rounded-2xl border border-[#18304f] bg-[#05070A] p-4 shadow-sm lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="text-sm font-semibold text-white">
              {rechercheEffectuee
                ? `${documentsFiltres.length} document${
                    documentsFiltres.length >
                    1
                      ? "s"
                      : ""
                  } trouvé${
                    documentsFiltres.length >
                    1
                      ? "s"
                      : ""
                  }`
                : "Aucune recherche effectuée"}
            </div>

            {rechercheEffectuee && (
              <div className="mt-1 text-xs text-slate-500">
                {documentsSelectionnes.length} sélectionné
                {documentsSelectionnes.length >
                1
                  ? "s"
                  : ""}
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() =>
                setFiltreOuvert(
                  (actuel) =>
                    !actuel
                )
              }
              className="inline-flex items-center gap-2 rounded-xl border border-[#29476b] bg-[#05070A] px-4 py-2.5 text-sm font-semibold text-slate-300 transition hover:border-[#1677FF]/60 hover:text-[#5da2ff]"
            >
              <FilterIcon />

              Filtres

              {nombreFiltresActifs >
                0 && (
                <span className="rounded-full bg-blue-600 px-2 py-0.5 text-xs text-white">
                  {
                    nombreFiltresActifs
                  }
                </span>
              )}
            </button>

            {documentsFiltres.length >
              0 && (
              <button
                type="button"
                onClick={
                  basculerSelectionTout
                }
                disabled={
                  telechargementActif
                }
                className="inline-flex items-center gap-2 rounded-xl border border-[#1677FF] bg-[#1677FF]/10 px-4 py-2.5 text-sm font-semibold text-[#5da2ff] transition hover:bg-[#1677FF]/20 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <CheckIcon />

                {tousLesDocumentsSelectionnes
                  ? "Tout désélectionner"
                  : `Tout sélectionner (${documentsFiltres.length})`}
              </button>
            )}

            {documentsSelectionnes.length >
              0 && (
              <button
                type="button"
                onClick={
                  telechargerSelection
                }
                disabled={
                  telechargementActif
                }
                className="inline-flex items-center gap-2 rounded-xl bg-black px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#0b1524] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <DownloadIcon />

                Télécharger (
                {
                  documentsSelectionnes.length
                }
                )
              </button>
            )}
          </div>
        </div>

        {/* ==================================================
            FILTRES
        ================================================== */}

        {filtreOuvert && (
          <div className="mb-6 rounded-2xl border border-[#18304f] bg-[#05070A] p-5 shadow-sm">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h2 className="text-base font-bold text-white">
                  Filtres de recherche
                </h2>

                <p className="mt-1 text-xs text-slate-500">
                  Affinez les documents affichés.
                </p>
              </div>

              <button
                type="button"
                onClick={
                  reinitialiserFiltres
                }
                className="text-sm font-medium text-[#5da2ff]"
              >
                Réinitialiser
              </button>
            </div>

            <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
              {/* NOMBRE */}

              <div>
                <label className="mb-2 block text-sm font-semibold text-slate-300">
                  Nombre de documents
                </label>

                <select
                  value={
                    nombreDocuments
                  }
                  onChange={(event) =>
                    setNombreDocuments(
                      Number(
                        event.target
                          .value
                      )
                    )
                  }
                  className="h-11 w-full rounded-xl border border-[#29476b] bg-[#05070A] px-3 text-sm outline-none focus:border-[#1677FF] focus:ring-4 focus:ring-[#1677FF]/20"
                >
                  <option value={5}>
                    5
                  </option>

                  <option value={10}>
                    10
                  </option>

                  <option value={20}>
                    20
                  </option>

                  <option value={30}>
                    30
                  </option>

                  <option value={50}>
                    50
                  </option>

                  <option value={100}>
                    100
                  </option>
                </select>
              </div>

              {/* TYPE */}

              <div>
                <label className="mb-2 block text-sm font-semibold text-slate-300">
                  Type de document
                </label>

                <div className="relative">
                  <select
                    value={
                      typeDocument
                    }
                    onChange={(event) =>
                      setTypeDocument(
                        event.target
                          .value
                      )
                    }
                    className="h-11 w-full appearance-none rounded-xl border border-[#29476b] bg-[#05070A] px-3 pr-10 text-sm outline-none focus:border-[#1677FF] focus:ring-4 focus:ring-[#1677FF]/20"
                  >
                    <option value="all">
                      Tous les types
                    </option>

                    <option value="article">
                      Article
                    </option>

                    <option value="thesis">
                      Mémoire / Thèse
                    </option>

                    <option value="conference">
                      Conférence
                    </option>

                    <option value="book">
                      Livre
                    </option>

                    <option value="other">
                      Autre
                    </option>
                  </select>

                  <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-500">
                    <ChevronDownIcon />
                  </div>
                </div>
              </div>

              {/* ANNÉE MIN */}

              <div>
                <label className="mb-2 block text-sm font-semibold text-slate-300">
                  Année minimale
                </label>

                <input
                  type="number"
                  value={anneeMin}
                  min={1900}
                  max={2100}
                  onChange={(event) =>
                    setAnneeMin(
                      Number(
                        event.target
                          .value
                      )
                    )
                  }
                  className="h-11 w-full rounded-xl border border-[#29476b] bg-[#05070A] px-3 text-sm outline-none focus:border-[#1677FF] focus:ring-4 focus:ring-[#1677FF]/20"
                />
              </div>

              {/* ANNÉE MAX */}

              <div>
                <label className="mb-2 block text-sm font-semibold text-slate-300">
                  Année maximale
                </label>

                <input
                  type="number"
                  value={anneeMax}
                  min={1900}
                  max={2100}
                  onChange={(event) =>
                    setAnneeMax(
                      Number(
                        event.target
                          .value
                      )
                    )
                  }
                  className="h-11 w-full rounded-xl border border-[#29476b] bg-[#05070A] px-3 text-sm outline-none focus:border-[#1677FF] focus:ring-4 focus:ring-[#1677FF]/20"
                />
              </div>
            </div>

            {/* SOURCES */}

            <div className="mt-6">
              <div className="mb-2 text-sm font-semibold text-slate-300">
                Sources
              </div>

              <div className="flex flex-wrap gap-2">
                {SOURCES.map(
                  (source) => {
                    const active =
                      sourcesSelectionnees.includes(
                        source
                      );

                    return (
                      <button
                        key={source}
                        type="button"
                        onClick={() =>
                          modifierSource(
                            source
                          )
                        }
                        className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
                          active
                            ? "border-[#1677FF] bg-blue-600 text-white"
                            : "border-[#29476b] bg-[#05070A] text-slate-300 hover:border-[#1677FF]/60 hover:text-[#5da2ff]"
                        }`}
                      >
                        {source}
                      </button>
                    );
                  }
                )}
              </div>

              <p className="mt-2 text-xs text-slate-500">
                Si aucune source n'est sélectionnée,
                les 3 sources sont interrogées
                automatiquement.
              </p>
            </div>

            {/* OPTIONS */}

            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-[#18304f] p-3 transition hover:border-blue-200">
                <input
                  type="checkbox"
                  checked={
                    openAccessSeulement
                  }
                  onChange={(event) =>
                    setOpenAccessSeulement(
                      event.target
                        .checked
                    )
                  }
                  className="h-4 w-4 accent-blue-600"
                />

                <div>
                  <div className="text-sm font-semibold text-slate-200">
                    Open Access uniquement
                  </div>

                  <div className="text-xs text-slate-500">
                    Afficher uniquement les documents en accès ouvert.
                  </div>
                </div>
              </label>

              <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-[#18304f] p-3 transition hover:border-blue-200">
                <input
                  type="checkbox"
                  checked={
                    pdfSeulement
                  }
                  onChange={(event) =>
                    setPdfSeulement(
                      event.target
                        .checked
                    )
                  }
                  className="h-4 w-4 accent-blue-600"
                />

                <div>
                  <div className="text-sm font-semibold text-slate-200">
                    PDF disponible uniquement
                  </div>

                  <div className="text-xs text-slate-500">
                    Afficher uniquement les documents ayant un lien PDF.
                  </div>
                </div>
              </label>
            </div>

            <div className="mt-5 rounded-xl bg-[#0B3D91]/20 p-3 text-xs leading-5 text-blue-300">
              Les changements de filtres affinent les documents déjà
              trouvés. Pour appliquer les nouveaux paramètres directement
              aux sources, relancez la recherche.
            </div>
          </div>
        )}

        {/* ==================================================
            ERREUR
        ================================================== */}

        {erreur && (
          <div className="mb-6 flex items-start justify-between gap-4 rounded-2xl border border-red-900 bg-red-950/50 p-4 text-sm text-red-300">
            <div>
              <div className="font-semibold">
                Attention
              </div>

              <div className="mt-1">
                {erreur}
              </div>
            </div>

            <button
              type="button"
              onClick={() =>
                setErreur("")
              }
              className="rounded-lg p-1 text-red-400 hover:bg-red-900/30"
            >
              <XIcon />
            </button>
          </div>
        )}

        {/* ==================================================
            PROGRESSION ZIP
        ================================================== */}

        {(telechargementActif ||
          progression ||
          telechargementTermine ||
          telechargementAnnule) && (
          <div className="mb-6 overflow-hidden rounded-2xl border border-[#18304f] bg-[#05070A] shadow-sm">
            <div className="p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white">
                    Téléchargement des documents
                  </h3>

                  <p className="mt-1 text-xs text-slate-500">
                    {progression?.message ||
                      (telechargementAnnule
                        ? "Téléchargement annulé."
                        : telechargementTermine
                        ? "Le téléchargement est terminé."
                        : "Préparation des fichiers PDF...")}
                  </p>

                  {progression?.etape && (
                    <p className="mt-1 text-xs font-medium text-[#5da2ff]">
                      {progression.etape}
                    </p>
                  )}
                </div>

                <div className="flex flex-wrap gap-2">
                  {/* PAUSE */}

                  {telechargementActif &&
                    !telechargementEnPause && (
                      <button
                        type="button"
                        onClick={
                          mettreEnPause
                        }
                        className="inline-flex items-center gap-2 rounded-xl border border-[#29476b] px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-[#020409]"
                      >
                        <PauseIcon />
                        Pause
                      </button>
                    )}

                  {/* REPRISE */}

                  {telechargementActif &&
                    telechargementEnPause && (
                      <button
                        type="button"
                        onClick={
                          reprendreTelechargement
                        }
                        className="inline-flex items-center gap-2 rounded-xl border border-[#1677FF]/60 px-3 py-2 text-xs font-semibold text-[#5da2ff] hover:bg-[#0B3D91]/20"
                      >
                        <PlayIcon />
                        Reprendre
                      </button>
                    )}

                  {/* ANNULER */}

                  {telechargementActif && (
                    <button
                      type="button"
                      onClick={
                        annulerTelechargement
                      }
                      className="inline-flex items-center gap-2 rounded-xl border border-red-900 px-3 py-2 text-xs font-semibold text-red-400 hover:bg-red-950/50"
                    >
                      <XIcon />
                      Annuler
                    </button>
                  )}

                  {/* RÉCUPÉRER ZIP */}

                  {telechargementTermine && (
                    <button
                      type="button"
                      onClick={
                        recupererZip
                      }
                      className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-[#0B3D91]"
                    >
                      <DownloadIcon />
                      Récupérer le ZIP
                    </button>
                  )}
                </div>
              </div>

              {/* BARRE DE PROGRESSION */}

              <div className="mt-6">
                <div className="mb-2 flex items-center justify-between text-xs font-medium text-slate-500">
                  <span>
                    {documentsTraites} /{" "}
                    {totalDocuments} documents traités
                  </span>

                  <span className="font-bold text-white">
                    {Math.round(
                      progressionPourcentage
                    )}
                    %
                  </span>
                </div>

                <div className="relative h-3 overflow-hidden rounded-full bg-[#0b1524]">
                  <div
                    className="h-full rounded-full bg-blue-600 transition-all duration-500 ease-out"
                    style={{
                      width: `${progressionPourcentage}%`,
                    }}
                  />
                </div>
              </div>

              {/* STATISTIQUES */}

              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                <div className="rounded-xl border border-[#18304f] bg-[#020409] p-3">
                  <div className="text-xs text-slate-500">
                    Documents traités
                  </div>

                  <div className="mt-1 text-lg font-bold text-white">
                    {documentsTraites} /{" "}
                    {totalDocuments}
                  </div>
                </div>

                <div className="rounded-xl border border-emerald-900/60 bg-emerald-950/20 p-3">
                  <div className="text-xs text-emerald-400">
                    PDF téléchargés
                  </div>

                  <div className="mt-1 text-lg font-bold text-emerald-300">
                    {pdfTelecharges}
                  </div>
                </div>

                <div className="rounded-xl border border-red-900/60 bg-red-950/20 p-3">
                  <div className="text-xs text-red-400">
                    Échecs
                  </div>

                  <div className="mt-1 text-lg font-bold text-red-300">
                    {pdfEchecs}
                  </div>
                </div>
              </div>

              {/* DOCUMENT EN COURS */}

              {progression?.message &&
                telechargementActif &&
                !telechargementEnPause && (
                  <div className="mt-4 rounded-xl border border-[#18304f] bg-[#020409] p-3">
                    <div className="text-xs font-semibold text-slate-500">
                      Document en cours
                    </div>

                    <div className="mt-1 truncate text-sm font-medium text-slate-200">
                      {progression.message.replace(
                        /^Téléchargement\s*:\s*/i,
                        ""
                      )}
                    </div>
                  </div>
                )}

              {/* PAUSE */}

              {telechargementEnPause && (
                <div className="mt-4 rounded-xl border border-amber-800/60 bg-amber-950/20 p-3 text-sm text-amber-300">
                  Le téléchargement est actuellement en pause.
                </div>
              )}

              {/* TERMINÉ */}

              {telechargementTermine &&
                progression && (
                  <div className="mt-4 rounded-xl border border-emerald-900/60 bg-emerald-950/20 p-4">
                    <div className="flex items-center gap-2 text-sm font-bold text-emerald-300">
                      <CheckIcon />
                      Téléchargement terminé
                    </div>

                    <p className="mt-1 text-xs text-emerald-400">
                      {pdfTelecharges} PDF téléchargé
                      {pdfTelecharges > 1
                        ? "s"
                        : ""}
                      {pdfEchecs > 0
                        ? ` — ${pdfEchecs} document${
                            pdfEchecs > 1
                              ? "s"
                              : ""
                          } non téléchargé${
                            pdfEchecs > 1
                              ? "s"
                              : ""
                          }.`
                        : "."}
                    </p>
                  </div>
                )}

              {/* ANNULÉ */}

              {telechargementAnnule && (
                <div className="mt-4 rounded-xl border border-red-900/60 bg-red-950/20 p-4 text-sm text-red-300">
                  Le téléchargement a été annulé.
                </div>
              )}

              {/* ERREUR */}

              {telechargementEnErreur &&
                progression?.erreur && (
                  <div className="mt-4 rounded-xl border border-red-900/60 bg-red-950/20 p-4 text-sm text-red-300">
                    {progression.erreur}
                  </div>
                )}
            </div>
          </div>
        )}

        {/* ==================================================
            RÉSULTATS
        ================================================== */}

        {chargement ? (
          <div className="rounded-2xl border border-[#18304f] bg-[#05070A] p-12 text-center shadow-sm">
            <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-[#18304f] border-t-blue-600" />

            <h2 className="mt-5 text-base font-bold text-white">
              Recherche en cours...
            </h2>

            <p className="mt-2 text-sm text-slate-500">
              Interrogation d'OpenAlex, HAL et Crossref.
            </p>
          </div>
        ) : !rechercheEffectuee ? (
          <div className="rounded-2xl border border-dashed border-[#29476b] bg-[#05070A] p-12 text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[#0B3D91]/20 text-[#5da2ff]">
              <SearchIcon />
            </div>

            <h2 className="mt-5 text-lg font-bold text-white">
              Commencez votre recherche
            </h2>

            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
              Saisissez un sujet scientifique ci-dessus pour rechercher
              des documents dans plusieurs bases scientifiques.
            </p>
          </div>
        ) : documentsFiltres.length ===
          0 ? (
          <div className="rounded-2xl border border-[#18304f] bg-[#05070A] p-12 text-center">
            <h2 className="text-lg font-bold text-white">
              Aucun résultat
            </h2>

            <p className="mt-2 text-sm text-slate-500">
              Essayez de modifier les filtres ou d'effectuer une nouvelle
              recherche.
            </p>
          </div>
        ) : (
          <>
            <div className="space-y-4">
              {documentsAffiches.map(
                (
                  document,
                  index
                ) => {
                  const indexGlobal =
                    (page - 1) *
                      documentsParPage +
                    index;

                  const selectionne =
                    documentEstSelectionne(
                      document,
                      indexGlobal
                    );

                  const typeLabel =
                    libelleTypeDocument(
                      document.type_document
                    );

                  return (
                    <article
                      key={cleDocument(
                        document,
                        indexGlobal
                      )}
                      className={`rounded-2xl border bg-[#05070A] p-5 shadow-sm transition ${
                        selectionne
                          ? "border-[#1677FF] ring-2 ring-[#1677FF]/20"
                          : "border-[#18304f] hover:border-[#29476b]"
                      }`}
                    >
                      <div className="flex gap-4">
                        <button
                          type="button"
                          onClick={() =>
                            modifierSelection(
                              document,
                              indexGlobal
                            )
                          }
                          className={`mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border transition ${
                            selectionne
                              ? "border-[#1677FF] bg-blue-600 text-white"
                              : "border-[#29476b] bg-[#05070A] text-transparent hover:border-[#1677FF]"
                          }`}
                          aria-label={
                            selectionne
                              ? "Désélectionner"
                              : "Sélectionner"
                          }
                        >
                          <CheckIcon />
                        </button>

                        <div className="min-w-0 flex-1">
                          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                            <div className="min-w-0">
                              <h2 className="text-base font-bold leading-6 text-white">
                                {document.titre ||
                                  "Titre indisponible"}
                              </h2>

                              <div className="mt-3 flex flex-wrap gap-2">
                                {document.source && (
                                  <span className="rounded-full bg-[#0b1524] px-3 py-1 text-xs font-medium text-slate-300">
                                    {document.source}
                                  </span>
                                )}

                                {typeLabel && (
                                  <span className="rounded-full bg-[#0B3D91]/20 px-3 py-1 text-xs font-medium text-[#5da2ff]">
                                    {typeLabel}
                                  </span>
                                )}

                                {document.annee && (
                                  <span className="rounded-full bg-[#0b1524] px-3 py-1 text-xs font-medium text-slate-300">
                                    {document.annee}
                                  </span>
                                )}

                                {document.open_access && (
                                  <span className="rounded-full bg-emerald-950/40 px-3 py-1 text-xs font-medium text-emerald-400">
                                    Open Access
                                  </span>
                                )}

                                {document.lien_pdf && (
                                  <span className="rounded-full bg-purple-950/40 px-3 py-1 text-xs font-medium text-purple-400">
                                    PDF
                                  </span>
                                )}

                                {typeof document.score ===
                                  "number" && (
                                  <span className="rounded-full bg-amber-950/40 px-3 py-1 text-xs font-medium text-amber-400">
                                    Score{" "}
                                    {
                                      document.score
                                    }
                                  </span>
                                )}
                              </div>
                            </div>

                            {document.journal && (
                              <div className="shrink-0 text-xs text-slate-500 lg:max-w-xs lg:text-right">
                                {
                                  document.journal
                                }
                              </div>
                            )}
                          </div>

                          {document.auteurs &&
                            document.auteurs
                              .length >
                              0 && (
                              <p className="mt-3 text-sm text-slate-500">
                                <span className="font-semibold text-slate-300">
                                  Auteurs :
                                </span>{" "}
                                {document.auteurs.join(
                                  ", "
                                )}
                              </p>
                            )}

                          {(document.resume ||
                            document.abstract) && (
                            <p className="mt-3 line-clamp-3 text-sm leading-6 text-slate-500">
                              {document.resume ||
                                document.abstract}
                            </p>
                          )}

                          {document.doi && (
                            <p className="mt-3 break-all text-xs text-slate-500">
                              <span className="font-semibold text-slate-300">
                                DOI :
                              </span>{" "}
                              {
                                document.doi
                              }
                            </p>
                          )}

                          <div className="mt-5 flex flex-wrap gap-2">
                            {document.lien_pdf && (
                              <a
                                href={
                                  document.lien_pdf
                                }
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#0B3D91]"
                              >
                                <DownloadIcon />
                                Voir le PDF
                              </a>
                            )}

                            {document.url && (
                              <a
                                href={
                                  document.url
                                }
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-2 rounded-xl border border-[#29476b] bg-[#05070A] px-4 py-2 text-xs font-semibold text-slate-300 transition hover:bg-[#020409]"
                              >
                                <ExternalIcon />
                                Source
                              </a>
                            )}
                          </div>
                        </div>
                      </div>
                    </article>
                  );
                }
              )}
            </div>

            {/* ==================================================
                PAGINATION
            ================================================== */}

            {totalPages > 1 && (
              <div className="mt-7 flex items-center justify-center gap-2">
                <button
                  type="button"
                  disabled={page === 1}
                  onClick={() =>
                    setPage(
                      (actuelle) =>
                        Math.max(
                          1,
                          actuelle - 1
                        )
                    )
                  }
                  className="rounded-xl border border-[#29476b] bg-[#05070A] px-4 py-2 text-sm font-medium text-slate-300 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Précédent
                </button>

                <span className="rounded-xl bg-[#0b1524] px-4 py-2 text-sm font-semibold text-slate-300">
                  Page {page} /{" "}
                  {totalPages}
                </span>

                <button
                  type="button"
                  disabled={
                    page ===
                    totalPages
                  }
                  onClick={() =>
                    setPage(
                      (actuelle) =>
                        Math.min(
                          totalPages,
                          actuelle + 1
                        )
                    )
                  }
                  className="rounded-xl border border-[#29476b] bg-[#05070A] px-4 py-2 text-sm font-medium text-slate-300 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Suivant
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {/* ==================================================
          FOOTER
      ================================================== */}

      <footer className="border-t border-[#18304f] bg-[#05070A]">
        <div className="mx-auto max-w-7xl px-5 py-6 text-center text-xs text-slate-500 lg:px-8">
          Scientific Document Finder — Recherche scientifique
          multi-sources
        </div>
      </footer>
    </main>
  );
}