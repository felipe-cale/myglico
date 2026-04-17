import { useEffect, useState } from "react";
import { fetchSemanticQueries, fetchSemanticResult } from "../api";
import StateBlock from "../components/StateBlock";

export default function SemanticPage() {
  const [queries, setQueries] = useState({});
  const [selected, setSelected] = useState("high_risk_days");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    fetchSemanticQueries()
      .then((payload) => {
        if (active) {
          setQueries(payload.queries);
        }
      })
      .catch((reason) => {
        if (active) {
          setError(reason);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchSemanticResult(selected)
      .then((payload) => {
        if (active) {
          setResult(payload);
        }
      })
      .catch((reason) => {
        if (active) {
          setError(reason);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [selected]);

  const rows = result?.results || [];
  const columns = rows.length ? Object.keys(rows[0]) : [];

  return (
    <div className="react-page">
      <section className="react-hero react-hero--compact">
        <div className="react-hero__content">
          <div className="react-badges">
            <span className="react-badge react-badge--brand">RDF</span>
            <span className="react-badge react-badge--blue">OWL</span>
            <span className="react-badge react-badge--green">SPARQL</span>
          </div>
          <p className="react-eyebrow">Workspace semantico</p>
          <h1>Consulta dinamica do grafo pela API</h1>
          <p>
            Esta tela React chama os endpoints semanticos do FastAPI e mantem o mesmo dominio conceitual do MVP
            original, mas com uma camada de navegacao e leitura mais apropriada para crescer.
          </p>
        </div>
      </section>

      <section className="react-panel">
        <div className="react-panel__header">
          <div>
            <p className="react-eyebrow">Consultas prontas</p>
            <h2>Escolha uma consulta</h2>
          </div>
          <div className="react-chip-row">
            {Object.keys(queries).map((queryName) => (
              <button
                key={queryName}
                type="button"
                onClick={() => setSelected(queryName)}
                className={`react-chip${selected === queryName ? " is-active" : ""}`}
              >
                {queryName}
              </button>
            ))}
          </div>
        </div>
        <pre className="react-code">{queries[selected]}</pre>
      </section>

      {loading ? (
        <StateBlock title="Executando consulta" description="Buscando bindings do grafo pela API do FastAPI." tone="info" />
      ) : error ? (
        <StateBlock title="Falha ao executar consulta" description="Nao foi possivel carregar os resultados semanticos." tone="danger" />
      ) : (
        <section className="react-panel">
          <div className="react-panel__header">
            <div>
              <p className="react-eyebrow">Resultados</p>
              <h2>Bindings retornados</h2>
            </div>
          </div>
          <div className="react-table-shell">
            <table className="react-table">
              <thead>
                <tr>
                  {columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${selected}-${index}`}>
                    {columns.map((column) => (
                      <td key={column}>{row[column]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
