import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchDashboardSummary, fetchPatients } from "../api";
import MetricCard from "../components/MetricCard";
import Pagination from "../components/Pagination";
import StateBlock from "../components/StateBlock";

const assetUrl = (path) => `${import.meta.env.BASE_URL}${path}`;
const JUSTIFIED_TEXT_STYLE = {
  textAlign: "justify",
  textJustify: "inter-word",
  hyphens: "auto",
  display: "block",
  width: "100%"
};

function formatNumber(value, suffix = "") {
  if (value === null || value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value) + suffix;
}

function getPatientSignal(patient) {
  if (patient.signal_label && patient.signal_tone) {
    return { label: patient.signal_label, tone: patient.signal_tone };
  }
  if (patient.pct_hyper >= 65 || patient.avg_glucose >= 185) {
    return { label: "Perfil Hiperglicêmico", tone: "alert" };
  }
  if (patient.pct_hypo >= 10) {
    return { label: "Perfil Hipoglicêmico", tone: "warning" };
  }
  return { label: "Perfil em Faixa", tone: "stable" };
}

const PROFILE_HELP = {
  all: {
    title: "Perfis de filtro",
    intro: "Os perfis abaixo organizam a lista por padrão glicêmico predominante no período analisado. Eles funcionam como triagem visual e não substituem avaliação clínica.",
    sections: [
      {
        title: "Perfil em Faixa",
        body:
          "Agrupa pacientes que não atingiram os limiares de perfil hiperglicêmico nem hipoglicêmico. Nas métricas da aplicação, a faixa usada como referência considera 70 a 180 mg/dL nas leituras gerais, 80 a 130 mg/dL nas leituras pré-refeição e valores abaixo de 180 mg/dL nas leituras pós-refeição."
      },
      {
        title: "Perfil Hiperglicêmico",
        body:
          "É aplicado quando a média glicêmica do período é maior ou igual a 185 mg/dL ou quando o tempo em alta é maior ou igual a 65%. O tempo em alta considera leituras iguais ou acima de 130 mg/dL nas medições pré-refeição e iguais ou acima de 180 mg/dL nas medições pós-refeição ou sem contexto específico."
      },
      {
        title: "Perfil Hipoglicêmico",
        body:
          "É aplicado quando o tempo em baixa é maior ou igual a 10% no período. O tempo em baixa considera leituras abaixo de 70 mg/dL."
      }
    ]
  },
  stable: {
    title: "Perfil em Faixa",
    intro:
      "Este filtro mostra pacientes que permaneceram fora dos critérios de perfil hiperglicêmico e hipoglicêmico na triagem atual.",
    sections: [
      {
        title: "Faixa considerada",
        body:
          "A referência usada nas métricas considera 70 a 180 mg/dL nas leituras gerais, 80 a 130 mg/dL nas leituras pré-refeição e valores abaixo de 180 mg/dL nas leituras pós-refeição."
      },
      {
        title: "Como o filtro entra aqui",
        body:
          "O paciente permanece neste grupo quando a média glicêmica do período fica abaixo de 185 mg/dL e o tempo em baixa fica abaixo de 10%."
      }
    ]
  },
  attention: {
    title: "Perfil Hiperglicêmico",
    intro: "Este filtro destaca pacientes com predominância de leituras elevadas no período analisado.",
    sections: [
      {
        title: "Limiar de classificação",
        body:
          "O perfil é aplicado quando a média glicêmica do período é maior ou igual a 185 mg/dL ou quando o tempo em alta é maior ou igual a 65%."
      },
      {
        title: "O que conta como alta",
        body:
          "O tempo em alta considera leituras iguais ou acima de 130 mg/dL nas medições pré-refeição e iguais ou acima de 180 mg/dL nas medições pós-refeição ou sem contexto específico."
      }
    ]
  },
  oscillation: {
    title: "Perfil Hipoglicêmico",
    intro: "Este filtro destaca pacientes com recorrência mais relevante de leituras em baixa no período.",
    sections: [
      {
        title: "Limiar de classificação",
        body: "O perfil é aplicado quando o tempo em baixa é maior ou igual a 10% no período."
      },
      {
        title: "O que conta como baixa",
        body: "O tempo em baixa considera leituras abaixo de 70 mg/dL."
      }
    ]
  }
};

function FilterHelpDialog({ signal, open, onClose }) {
  const dialogRef = useRef(null);
  const content = PROFILE_HELP[signal] || PROFILE_HELP.all;

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handlePointerDown = (event) => {
      if (!dialogRef.current?.contains(event.target)) {
        onClose();
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  return (
    <div className="react-dialog-backdrop" role="presentation">
      <div
        className="react-dialog react-dialog--profile-help"
        role="dialog"
        aria-modal="true"
        aria-labelledby="profile-help-title"
        ref={dialogRef}
      >
        <div className="react-dialog__header">
          <div>
            <p className="react-eyebrow">Ajuda do filtro</p>
            <h3 id="profile-help-title">{content.title}</h3>
          </div>
          <button type="button" className="react-dialog__close" onClick={onClose} aria-label="Fechar explicação dos perfis">
            ×
          </button>
        </div>
        <div className="react-dialog__body">
          <p style={JUSTIFIED_TEXT_STYLE}>{content.intro}</p>
          <div className="react-dialog__sections">
            {content.sections.map((section) => (
              <section key={section.title} className="react-dialog__section">
                <h4>{section.title}</h4>
                <p style={JUSTIFIED_TEXT_STYLE}>{section.body}</p>
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function OverviewPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [summary, setSummary] = useState(null);
  const [patients, setPatients] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [summaryError, setSummaryError] = useState(null);
  const [patientsError, setPatientsError] = useState(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [copiedPatientId, setCopiedPatientId] = useState("");

  const currentPage = Number(searchParams.get("page") || "1");
  const currentQuery = searchParams.get("q") || "";
  const currentSignal = searchParams.get("signal") || "all";
  const [searchValue, setSearchValue] = useState(currentQuery);
  const deferredSearch = useDeferredValue(searchValue);

  useEffect(() => {
    setSearchValue(currentQuery);
  }, [currentQuery]);

  useEffect(() => {
    let active = true;
    setLoadingSummary(true);
    setSummaryError(null);
    fetchDashboardSummary()
      .then((data) => {
        if (active) {
          setSummary(data);
        }
      })
      .catch((error) => {
        if (active) {
          setSummaryError(error);
        }
      })
      .finally(() => {
        if (active) {
          setLoadingSummary(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const nextQuery = deferredSearch.trim();
    if (nextQuery === currentQuery) {
      return;
    }
    startTransition(() => {
      const next = new URLSearchParams(searchParams);
      if (nextQuery) {
        next.set("q", nextQuery);
      } else {
        next.delete("q");
      }
      next.set("page", "1");
      setSearchParams(next);
    });
  }, [currentQuery, deferredSearch, searchParams, setSearchParams]);

  useEffect(() => {
    let active = true;
    setLoadingPatients(true);
    setPatientsError(null);
    fetchPatients({ page: currentPage, pageSize: 12, query: currentQuery, signal: currentSignal })
      .then((data) => {
        if (active) {
          setPatients(data);
        }
      })
      .catch((error) => {
        if (active) {
          setPatientsError(error);
        }
      })
      .finally(() => {
        if (active) {
          setLoadingPatients(false);
        }
      });
    return () => {
      active = false;
    };
  }, [currentPage, currentQuery, currentSignal]);

  const artifactLinks = useMemo(() => {
    if (!summary) {
      return [];
    }
    return [
      { label: "Ver origem dos dados", href: summary.links.latest_batch.provenance_json },
      { label: "Abrir histórico da análise", href: summary.links.latest_run.provenance_ttl },
      { label: "Consultar base estruturada", href: summary.links.latest_run.semantic_ttl }
    ].filter((item) => Boolean(item.href));
  }, [summary]);

  function handlePageChange(page) {
    const next = new URLSearchParams(searchParams);
    next.set("page", String(page));
    setSearchParams(next);
  }

  function handleSignalChange(signal) {
    const next = new URLSearchParams(searchParams);
    if (signal === "all") {
      next.delete("signal");
    } else {
      next.set("signal", signal);
    }
    next.set("page", "1");
    setSearchParams(next);
  }

  async function handleCopyShortId(patientId, shortId) {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(shortId);
      } else {
        const helper = document.createElement("textarea");
        helper.value = shortId;
        helper.setAttribute("readonly", "");
        helper.style.position = "absolute";
        helper.style.left = "-9999px";
        document.body.appendChild(helper);
        helper.select();
        document.execCommand("copy");
        document.body.removeChild(helper);
      }
      setCopiedPatientId(patientId);
      window.setTimeout(() => {
        setCopiedPatientId((current) => (current === patientId ? "" : current));
      }, 1800);
    } catch (error) {
      console.error("Nao foi possivel copiar o codigo do paciente.", error);
    }
  }

  const visiblePatients = useMemo(() => patients?.patients || [], [patients]);

  const signalFilters = [
    { value: "all", label: "Todos" },
    { value: "stable", label: "Perfil em Faixa" },
    { value: "attention", label: "Perfil Hiperglicêmico" },
    { value: "oscillation", label: "Perfil Hipoglicêmico" }
  ];

  return (
    <div className="react-page">
      <section className="react-hero">
        <div className="react-hero__content">
          <div className="react-badges">
            <span className="react-badge react-badge--brand">Acompanhamento diário</span>
            <span className="react-badge react-badge--green">Leitura clínica</span>
            <span className="react-badge react-badge--blue">Visão contínua</span>
          </div>
          <p className="react-eyebrow">Painel inicial</p>
          <h1>Acompanhe a saúde glicêmica com mais clareza</h1>
          <p>
            Visualize rapidamente quem está em acompanhamento, identifique padrões importantes e aprofunde a leitura
            de cada pessoa com contexto suficiente para apoiar decisões seguras.
          </p>
          <div className="react-actions">
            {artifactLinks.map((link) => (
              <a key={link.label} href={link.href} className="react-button react-button--ghost">
                {link.label}
              </a>
            ))}
          </div>
        </div>
        <div className="react-hero__visual">
          <img src={assetUrl("img/myglico-logo.png")} alt="Identidade MyGlico" />
        </div>
      </section>

      {loadingSummary ? (
        <StateBlock title="Carregando painel" description="Estamos preparando a visão mais recente da base acompanhada." tone="info" />
      ) : summaryError ? (
        <StateBlock title="Nao foi possivel carregar o painel" description="Tivemos um problema ao montar o resumo inicial deste ambiente." tone="danger" />
      ) : (
        <section className="react-grid react-grid--metrics">
          <MetricCard label="Pessoas acompanhadas" value={summary.metrics.patient_count} helper="Base pronta para acompanhamento contínuo." tone="blue" />
          <MetricCard label="Registros de glicemia" value={summary.metrics.normalized_count} helper="Leituras disponíveis para consulta e comparação." tone="cyan" />
          <MetricCard label="Dias analisados" value={summary.metrics.indicator_count} helper="Períodos consolidados para leitura clínica." tone="green" />
          <MetricCard label="Alertas de qualidade" value={summary.metrics.issue_count} helper="Pontos que merecem validação ou revisão." tone="yellow" />
        </section>
      )}

      <section className="react-panel">
        <div className="react-panel__header">
          <div className="react-panel__header-copy">
            <p className="react-eyebrow">Pessoas acompanhadas</p>
            <h2>Encontre um paciente em segundos</h2>
            <p>Busque por nome ou código do paciente e abra rapidamente o painel individual de quem precisa da sua atenção.</p>
          </div>
          <div className="react-patient-toolbar">
            <div className="react-patient-filter-row">
              <label className="react-select-field">
                <span>Filtrar por perfil</span>
                <select value={currentSignal} onChange={(event) => handleSignalChange(event.target.value)} aria-label="Filtrar pacientes por perfil">
                  {signalFilters.map((filter) => (
                    <option key={filter.value} value={filter.value}>
                      {filter.label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="react-help-button"
                aria-label="Explicar perfis do filtro"
                onClick={() => setHelpOpen(true)}
              >
                ?
              </button>
            </div>
            <div className="react-search react-search--patients">
              <input
                type="search"
                value={searchValue}
                onChange={(event) => setSearchValue(event.target.value)}
                placeholder="Buscar por nome ou código"
                aria-label="Buscar paciente"
              />
            </div>
          </div>
        </div>

        {loadingPatients ? (
          <StateBlock title="Carregando pacientes" description="Estamos atualizando a lista de pessoas acompanhadas." tone="info" />
        ) : patientsError ? (
          <StateBlock title="Nao foi possivel carregar a lista" description="Houve um problema ao trazer os pacientes deste ambiente." tone="danger" />
        ) : patients && patients.patients.length ? (
          <>
            <div className="react-patient-grid">
              {visiblePatients.map((patient) => {
                const signal = getPatientSignal(patient);
                const copied = copiedPatientId === patient.id;
                return (
                  <article key={patient.id} className="react-patient-card">
                    <div className="react-patient-card__identity">
                      <h3>{patient.display_name}</h3>
                      <div className="react-patient-code">
                        <div className="react-patient-code__content">
                          <span className="react-patient-code__label">Código do paciente</span>
                          <strong className="react-patient-code__value">{patient.short_id}</strong>
                        </div>
                        <button
                          type="button"
                          className={`react-patient-code__copy${copied ? " is-copied" : ""}`}
                          aria-label={`Copiar código ${patient.short_id}`}
                          onClick={() => handleCopyShortId(patient.id, patient.short_id)}
                        >
                          {copied ? "Copiado" : "Copiar"}
                        </button>
                      </div>
                      <span className={`react-patient-card__signal react-patient-card__signal--${signal.tone}`}>{signal.label}</span>
                      <p>{patient.days_observed} dias com leituras disponíveis</p>
                    </div>
                    <dl className="react-patient-card__metrics">
                      <div className="react-patient-card__metric-row">
                        <dt>Média do período</dt>
                        <dd>{patient.avg_glucose != null ? `${formatNumber(patient.avg_glucose)} mg/dL` : "-"}</dd>
                      </div>
                      <div className="react-patient-card__metric-row">
                        <dt>Tempo em baixa</dt>
                        <dd>{formatNumber(patient.pct_hypo, "%")}</dd>
                      </div>
                      <div className="react-patient-card__metric-row">
                        <dt>Tempo em alta</dt>
                        <dd>{formatNumber(patient.pct_hyper, "%")}</dd>
                      </div>
                    </dl>
                    <Link to={`/patients/${patient.id}`} className="react-patient-card__footer">
                      <span>Abrir painel do paciente</span>
                    </Link>
                  </article>
                );
              })}
            </div>
            {visiblePatients.length ? (
              <div className="react-panel__footer">
                <span>
                  Página {patients.page} de {patients.pages}, com {patients.count} pacientes encontrados.
                </span>
                <Pagination page={patients.page} pages={patients.pages} onPageChange={handlePageChange} />
              </div>
            ) : (
              <StateBlock title="Nenhum paciente neste filtro" description="Tente outro status ou ajuste a busca para ampliar os resultados." />
            )}
          </>
        ) : (
          <StateBlock title="Nenhum paciente encontrado" description="Tente buscar por outro nome ou identificador para continuar." />
        )}
      </section>
      <FilterHelpDialog signal={currentSignal} open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
