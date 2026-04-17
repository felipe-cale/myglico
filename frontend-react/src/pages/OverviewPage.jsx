import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchDashboardSummary, fetchPatients } from "../api";
import MetricCard from "../components/MetricCard";
import Pagination from "../components/Pagination";
import StateBlock from "../components/StateBlock";

function formatNumber(value, suffix = "") {
  if (value === null || value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value) + suffix;
}

export default function OverviewPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [summary, setSummary] = useState(null);
  const [patients, setPatients] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [summaryError, setSummaryError] = useState(null);
  const [patientsError, setPatientsError] = useState(null);

  const currentPage = Number(searchParams.get("page") || "1");
  const currentQuery = searchParams.get("q") || "";
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
    fetchPatients({ page: currentPage, pageSize: 12, query: currentQuery })
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
  }, [currentPage, currentQuery]);

  const artifactLinks = useMemo(() => {
    if (!summary) {
      return [];
    }
    return [
      { label: "Import PROV JSON", href: summary.links.latest_batch.provenance_json },
      { label: "Analytics PROV TTL", href: summary.links.latest_run.provenance_ttl },
      { label: "Grafo RDF", href: summary.links.latest_run.semantic_ttl }
    ].filter((item) => Boolean(item.href));
  }, [summary]);

  function handlePageChange(page) {
    const next = new URLSearchParams(searchParams);
    next.set("page", String(page));
    setSearchParams(next);
  }

  return (
    <div className="react-page">
      <section className="react-hero">
        <div className="react-hero__content">
          <div className="react-badges">
            <span className="react-badge react-badge--brand">React principal</span>
            <span className="react-badge react-badge--green">FastAPI</span>
            <span className="react-badge react-badge--blue">Paginacao real</span>
          </div>
          <p className="react-eyebrow">Camada principal do produto</p>
          <h1>Interface React dinamica para o MyGlico</h1>
          <p>
            Esta interface consome o FastAPI em tempo real e agora ocupa a entrada principal do ambiente. A listagem
            de pacientes ja funciona com paginacao, busca e navegacao para o detalhamento analitico, enquanto a
            versao anterior segue disponivel de forma discreta para comparacao e homologacao.
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
          <img src="/static/img/myglico-logo.png" alt="Identidade MyGlico" />
        </div>
      </section>

      {loadingSummary ? (
        <StateBlock title="Carregando dashboard" description="Buscando os indicadores consolidados do FastAPI." tone="info" />
      ) : summaryError ? (
        <StateBlock title="Falha ao carregar dashboard" description="Nao foi possivel obter o resumo principal da API." tone="danger" />
      ) : (
        <section className="react-grid react-grid--metrics">
          <MetricCard label="Pacientes importados" value={summary.metrics.patient_count} helper="Base pronta para exploracao." tone="blue" />
          <MetricCard label="Eventos normalizados" value={summary.metrics.normalized_count} helper="Dados preparados para analytics." tone="cyan" />
          <MetricCard label="Indicadores diarios" value={summary.metrics.indicator_count} helper="Sintese disponivel na API." tone="green" />
          <MetricCard label="Issues de qualidade" value={summary.metrics.issue_count} helper="Apontamentos de ingestao rastreados." tone="yellow" />
        </section>
      )}

      <section className="react-panel">
        <div className="react-panel__header">
          <div>
            <p className="react-eyebrow">Pacientes</p>
            <h2>Listagem dinamica com paginacao</h2>
            <p>Busca por nome, arquivo ou codigo de origem, tudo vindo do FastAPI.</p>
          </div>
          <div className="react-search">
            <input
              type="search"
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
              placeholder="Buscar paciente"
              aria-label="Buscar paciente"
            />
          </div>
        </div>

        {loadingPatients ? (
          <StateBlock title="Carregando pacientes" description="Consultando a listagem paginada na API." tone="info" />
        ) : patientsError ? (
          <StateBlock title="Falha ao carregar pacientes" description="Nao foi possivel buscar a listagem paginada." tone="danger" />
        ) : patients && patients.patients.length ? (
          <>
            <div className="react-patient-grid">
              {patients.patients.map((patient) => (
                <Link key={patient.id} to={`/patients/${patient.id}`} className="react-patient-card">
                  <div className="react-patient-card__top">
                    <span className="react-patient-card__file">{patient.source_file}</span>
                    <span className="react-patient-card__id">#{patient.id}</span>
                  </div>
                  <h3>{patient.display_name}</h3>
                  <dl>
                    <div>
                      <dt>Dias</dt>
                      <dd>{patient.days_observed}</dd>
                    </div>
                    <div>
                      <dt>Media</dt>
                      <dd>{patient.avg_glucose != null ? `${formatNumber(patient.avg_glucose)} mg/dL` : "-"}</dd>
                    </div>
                    <div>
                      <dt>Hipo</dt>
                      <dd>{formatNumber(patient.pct_hypo, "%")}</dd>
                    </div>
                    <div>
                      <dt>Hiper</dt>
                      <dd>{formatNumber(patient.pct_hyper, "%")}</dd>
                    </div>
                  </dl>
                </Link>
              ))}
            </div>
            <div className="react-panel__footer">
              <span>
                Mostrando pagina {patients.page} de {patients.pages} com {patients.count} pacientes.
              </span>
              <Pagination page={patients.page} pages={patients.pages} onPageChange={handlePageChange} />
            </div>
          </>
        ) : (
          <StateBlock title="Nenhum paciente encontrado" description="A busca atual nao retornou resultados." />
        )}
      </section>
    </div>
  );
}
