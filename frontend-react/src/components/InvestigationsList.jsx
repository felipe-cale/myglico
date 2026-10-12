import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { fetchInvestigations, fetchInvestigationDetail, createInvestigation, fetchDoctorLinks, fetchAtypicalDays } from "../api";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import InvestigationOrigin from "./InvestigationOrigin";
import StateBlock from "./StateBlock";

function formatDate(value, locale) {
  if (!value) return "";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(parsed);
}

async function loadUnreadCounts(items) {
  const entries = await Promise.all(items.map(async (inv) => {
    if (typeof inv.unread_count === "number") return [inv.id, inv.unread_count];
    try {
      const detail = await fetchInvestigationDetail(inv.id, { page_size: 1 });
      return [inv.id, detail?.unread_count ?? 0];
    } catch {
      return [inv.id, null];
    }
  }));
  return Object.fromEntries(entries);
}

export default function InvestigationsList() {
  const { t, i18n } = useTranslation();
  const { session } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const sectionRef = useRef(null);
  const atypicalSelectRef = useRef(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [investigations, setInvestigations] = useState([]);
  const [unreadById, setUnreadById] = useState({});
  const [listStatus, setListStatus] = useState("loading");
  const [showNew, setShowNew] = useState(false);
  const [links, setLinks] = useState([]);
  const [atypicalDays, setAtypicalDays] = useState([]);
  const [selectedAtypicalIds, setSelectedAtypicalIds] = useState([]);

  const [selectedLink, setSelectedLink] = useState("");
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const atypicalDayEventIds = searchParams.getAll("atypical_day_event_id");
  const atypicalDayEventId = atypicalDayEventIds[0] || "";
  const atypicalPatientId = searchParams.get("patient_id");
  const isPatient = session?.account?.roles?.includes("patient");

  const loadData = async () => {
    try {
      const inv = await fetchInvestigations();
      const items = inv.investigations || inv || [];
      setInvestigations(items);
      setListStatus("ready");
      loadUnreadCounts(items).then(setUnreadById);
    } catch {
      setListStatus("error");
    }
    try {
      const lks = await fetchDoctorLinks();
      setLinks((lks.links || lks || []).filter((link) => link.status === "active"));
    } catch {
      setLinks([]);
    }
  };

  useEffect(() => { loadData(); }, []);

  useEffect(() => {
    if (atypicalDayEventId) setShowNew(true);
  }, [atypicalDayEventId]);

  useEffect(() => {
    setSelectedAtypicalIds(atypicalDayEventIds);
  }, [location.search]);

  useEffect(() => {
    if (!atypicalPatientId || isPatient || selectedLink) return;
    const match = links.find((link) => link.patient_id === atypicalPatientId);
    if (match) setSelectedLink(String(match.id));
  }, [atypicalPatientId, isPatient, links, selectedLink]);

  useEffect(() => {
    const selectedAssociation = links.find((link) => String(link.id) === String(selectedLink));
    const patientId = isPatient ? session?.patient?.id : selectedAssociation?.patient_id;
    if (!patientId) {
      setAtypicalDays([]);
      return;
    }
    let active = true;
    fetchAtypicalDays(patientId).then((data) => {
      if (active) setAtypicalDays(data?.days || []);
    }).catch(() => {
      if (active) setAtypicalDays([]);
    });
    return () => { active = false; };
  }, [isPatient, links, selectedLink, session?.patient?.id]);

  useEffect(() => {
    if (location.hash === "#investigations") {
      sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [location.hash, listStatus]);

  useEffect(() => {
    const closeOnOutsidePointer = (event) => {
      const selector = atypicalSelectRef.current;
      if (selector?.open && !selector.contains(event.target)) selector.open = false;
    };
    const closeOnEscape = (event) => {
      if (event.key === "Escape" && atypicalSelectRef.current?.open) {
        atypicalSelectRef.current.open = false;
      }
    };
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      const link = links.find(l => String(l.id) === String(selectedLink));
      if (!link) return;
      setError("");
      const payload = {
        title,
        initial_message: message
      };
      if (isPatient) payload.doctor_id = link.doctor_id;
      else payload.patient_id = link.patient_id;
      if (selectedAtypicalIds.length) payload.atypical_day_event_ids = selectedAtypicalIds;
      const result = await createInvestigation(payload);
      setShowNew(false);
      setTitle(""); setMessage("");
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete("atypical_day_event_id");
      nextParams.delete("patient_id");
      setSearchParams(nextParams, { replace: true });
      loadData();
      if (result.investigation?.id) navigate(`/investigations/${result.investigation.id}`);
    } catch { setError(t(isPatient ? "cscw.openFailedPatient" : "cscw.openFailed")); }
  };

  const handleCancelCreate = () => {
    setShowNew(false);
    setSelectedLink("");
    setTitle("");
    setMessage("");
    setSelectedAtypicalIds([]);
    setError("");
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete("atypical_day_event_id");
    nextParams.delete("patient_id");
    setSearchParams(nextParams, { replace: true });
  };

  const counterpartName = (inv) =>
    inv.counterpart?.name || inv.counterpart?.display_name || inv.counterpart?.short_id || t("common.dash");

  return (
    <section id="investigations" ref={sectionRef} className="react-panel react-investigations" aria-labelledby="investigations-title">
      <div className="react-panel__header">
        <div className="react-panel__header-copy">
          <p className="react-eyebrow">{t("cscw.panelEyebrow")}</p>
          <h2 id="investigations-title">{isPatient ? t("cscw.myInvestigations") : t("cscw.investigations")}</h2>
          <p>{isPatient ? t("cscw.panelBodyPatient") : t("cscw.panelBodyDoctor")}</p>
        </div>
        <button
          type="button"
          onClick={() => setShowNew(!showNew)}
          className={`react-button${showNew ? " react-button--ghost" : ""}`}
          aria-expanded={showNew}
        >
          {t(isPatient ? "cscw.newPatient" : "cscw.newDoctor")}
        </button>
      </div>

      {showNew && (
        <div className="react-subpanel">
          <div className="react-subpanel__copy">
            <h3>{t(isPatient ? "cscw.newTitlePatient" : "cscw.newTitleDoctor")}</h3>
            <p>{t("cscw.newBody")}</p>
            {selectedAtypicalIds.length > 0 && <span className="react-badge react-badge--blue react-badge--compact">{t("cscw.selectedAtypicalCount", { count: selectedAtypicalIds.length })}</span>}
          </div>
          {links.length === 0 ? (
            <div role="status">
              <StateBlock title={isPatient ? t("cscw.noActiveLinkPatient") : t("cscw.noActiveLinkDoctor")} tone="info" />
            </div>
          ) : (
            <form onSubmit={handleCreate} className="react-form react-form--investigation">
              <div className="react-form__row">
                <label className="react-select-field">
                  <span>{t("cscw.association")}</span>
                    <select value={selectedLink} onChange={e => { setSelectedLink(e.target.value); setSelectedAtypicalIds([]); }} required>
                    <option value="">{t("cscw.selectAssociation")}</option>
                    {links.map(l => (
                      <option key={l.id} value={l.id}>
                        {isPatient ? l.doctor?.name : l.patient?.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="react-field">
                  <span>{t("cscw.subject")}</span>
                  <input type="text" value={title} onChange={e => setTitle(e.target.value)} required />
                </label>
              </div>
              <fieldset className="react-atypical-association">
                  <legend>{t("cscw.associateDays")}</legend>
                  <p>{t("cscw.associateDaysHint")}</p>
                  <details ref={atypicalSelectRef} className="react-atypical-select">
                    <summary>
                      <span>{selectedAtypicalIds.length
                        ? t("cscw.relatedAtypicalCount", { count: selectedAtypicalIds.length })
                        : t("cscw.notRelatedAtypical")}</span>
                    </summary>
                    <div className="react-atypical-select__options">
                      <button
                        type="button"
                        className={`react-atypical-select__empty${selectedAtypicalIds.length ? "" : " is-selected"}`}
                        aria-pressed={selectedAtypicalIds.length === 0}
                        onClick={() => setSelectedAtypicalIds([])}
                      >
                        {t("cscw.notRelatedAtypical")}
                      </button>
                      {atypicalDays.length === 0 ? (
                        <small>{t("cscw.noAtypicalAvailable")}</small>
                      ) : (
                        <ul>
                          {atypicalDays.map((day) => (
                            <li key={day.indicator_id}>
                              <label>
                                <input
                                  type="checkbox"
                                  checked={selectedAtypicalIds.includes(day.indicator_id)}
                                  onChange={() => setSelectedAtypicalIds((current) => current.includes(day.indicator_id)
                                    ? current.filter((id) => id !== day.indicator_id)
                                    : [...current, day.indicator_id])}
                                />
                                <span>{formatDate(day.date, i18n.language)}{day.reason_summary ? ` · ${day.reason_summary}` : ""}</span>
                              </label>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </details>
              </fieldset>
              <label className="react-field">
                <span>{t("cscw.message")}</span>
                <textarea value={message} onChange={e => setMessage(e.target.value)} required rows={4} />
              </label>
              <div className="react-form__actions">
                <button type="button" className="react-button react-button--ghost" onClick={handleCancelCreate}>
                  {t("dashboard.cancel")}
                </button>
                <button type="submit" className="react-button">
                  {t("cscw.send")}
                </button>
              </div>
            </form>
          )}
        </div>
      )}
      {error && <p className="react-form-message is-error" role="alert">{error}</p>}

      {listStatus === "loading" ? (
        <div role="status">
          <StateBlock title={t(isPatient ? "cscw.loadingListPatient" : "cscw.loadingList")} tone="info" />
        </div>
      ) : listStatus === "error" ? (
        <div role="alert">
          <StateBlock title={t(isPatient ? "cscw.listFailedPatient" : "cscw.listFailed")} tone="danger" />
        </div>
      ) : investigations.length === 0 ? (
        <StateBlock title={t(isPatient ? "cscw.emptyTitlePatient" : "cscw.emptyTitleDoctor")} description={isPatient ? t("cscw.emptyPatient") : t("cscw.emptyDoctor")} />
      ) : (
        <ul className="react-investigation-grid">
          {investigations.map(inv => {
            const unread = unreadById[inv.id];
            return (
              <li key={inv.id} className={`react-investigation-card${unread ? " has-unread" : ""}`}>
                <div className="react-investigation-card__header">
                  <h3>{inv.title}</h3>
                  {unread > 0 && (
                    <span className="react-badge react-badge--count" aria-label={t("cscw.unreadAria", { count: unread })}>
                      {t("cscw.unreadCount", { count: unread })}
                    </span>
                  )}
                </div>
                <p className="react-investigation-card__meta">
                  {t(isPatient ? "cscw.counterpartDoctor" : "cscw.counterpartPatient")}: <strong>{counterpartName(inv)}</strong>
                  {" · "}
                  {t("cscw.openedAt", { date: formatDate(inv.opened_at, i18n.language) })}
                </p>
                <div className="react-chip-row react-investigation-card__chips">
                  <span className={`react-status-chip react-status-chip--${inv.status}`}>
                    {t(`cscw.status.${inv.status}`, { defaultValue: inv.status })}
                  </span>
                  {inv.status === "open" ? (
                    <span className="react-badge react-badge--soft react-badge--compact">
                      {t("cscw.awaitingChip", { role: inv.awaiting_role ? t(`cscw.roles.${inv.awaiting_role}`, { defaultValue: inv.awaiting_role }) : t("cscw.nobody") })}
                    </span>
                  ) : null}
                </div>
                <InvestigationOrigin investigation={inv} />
                <Link to={`/investigations/${inv.id}`} className="react-patient-card__footer react-investigation-card__footer">
                  <span>{t("cscw.openConversation")}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
