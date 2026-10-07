import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { fetchInvestigations, fetchInvestigationDetail, createInvestigation, fetchDoctorLinks } from "../api";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

function formatDate(value, locale) {
  if (!value) return "";
  const parsed = new Date(value);
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
  const [searchParams, setSearchParams] = useSearchParams();
  const [investigations, setInvestigations] = useState([]);
  const [unreadById, setUnreadById] = useState({});
  const [listStatus, setListStatus] = useState("loading");
  const [showNew, setShowNew] = useState(false);
  const [links, setLinks] = useState([]);

  // form
  const [selectedLink, setSelectedLink] = useState("");
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const atypicalDayEventId = searchParams.get("atypical_day_event_id");
  const atypicalPatientId = searchParams.get("patient_id");
  const isPatient = session?.account?.roles?.includes("patient");

  const loadData = async () => {
    try {
      const inv = await fetchInvestigations();
      const items = inv.investigations || inv || [];
      setInvestigations(items);
      setListStatus("ready");
      loadUnreadCounts(items).then(setUnreadById);
    } catch(e) {
      setListStatus("error");
    }
    try {
      const lks = await fetchDoctorLinks();
      setLinks((lks.links || lks || []).filter((link) => link.status === "active"));
    } catch(e) {}
  };

  useEffect(() => { loadData(); }, []);

  useEffect(() => {
    if (atypicalDayEventId) setShowNew(true);
  }, [atypicalDayEventId]);

  useEffect(() => {
    if (!atypicalPatientId || isPatient || selectedLink) return;
    const match = links.find((link) => link.patient_id === atypicalPatientId);
    if (match) setSelectedLink(String(match.id));
  }, [atypicalPatientId, isPatient, links, selectedLink]);

  useEffect(() => {
    if (location.hash === "#investigations") {
      sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [location.hash, listStatus]);

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
      if (atypicalDayEventId) payload.atypical_day_event_id = atypicalDayEventId;
      const result = await createInvestigation(payload);
      setShowNew(false);
      setTitle(""); setMessage("");
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete("atypical_day_event_id");
      nextParams.delete("patient_id");
      setSearchParams(nextParams, { replace: true });
      loadData();
      if (result.investigation?.id) navigate(`/investigations/${result.investigation.id}`);
    } catch(e) { setError(t("cscw.openFailed")); }
  };

  const counterpartName = (inv) =>
    inv.counterpart?.name || inv.counterpart?.display_name || inv.counterpart?.short_id || t("common.dash");

  return (
    <section id="investigations" ref={sectionRef} style={{ marginTop: '2rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3>{t("cscw.investigations")}</h3>
        <button onClick={() => setShowNew(!showNew)} className="react-button" aria-expanded={showNew}>
          {t("cscw.new")}
        </button>
      </div>

      {showNew && (
        <form onSubmit={handleCreate} style={{ background: '#f0f0f0', padding: '1rem', marginTop: '1rem', borderRadius: '4px', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {atypicalDayEventId && <p className="react-badge react-badge--blue">{t("cscw.fromAtypicalDay")}</p>}
          {links.length === 0 ? (
            <p role="status">{isPatient ? t("cscw.noActiveLinkPatient") : t("cscw.noActiveLinkDoctor")}</p>
          ) : (
            <>
              <label className="react-select-field">
                <span>{t("cscw.association")}</span>
                <select value={selectedLink} onChange={e => setSelectedLink(e.target.value)} required>
                  <option value="">{t("cscw.selectAssociation")}</option>
                  {links.map(l => (
                    <option key={l.id} value={l.id}>
                      {isPatient ? l.doctor?.name : l.patient?.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="react-select-field">
                <span>{t("cscw.subject")}</span>
                <input type="text" value={title} onChange={e => setTitle(e.target.value)} required />
              </label>
              <label className="react-select-field">
                <span>{t("cscw.message")}</span>
                <textarea value={message} onChange={e => setMessage(e.target.value)} required rows={4} />
              </label>
              <button type="submit" className="react-button" style={{ background: '#005fcc', color: '#fff', border: 'none' }}>
                {t("cscw.send")}
              </button>
            </>
          )}
        </form>
      )}
      {error && <p role="alert">{error}</p>}

      <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {listStatus === "loading" ? (
          <p role="status">{t("common.loading")}</p>
        ) : listStatus === "error" ? (
          <p role="alert">{t("cscw.listFailed")}</p>
        ) : investigations.length === 0 ? <p>{t("cscw.empty")}</p> : investigations.map(inv => {
          const unread = unreadById[inv.id];
          return (
            <article key={inv.id} className={`react-investigation-card${unread ? " has-unread" : ""}`}>
              <div className="react-investigation-card__header">
                <strong>{inv.title}</strong>
                {unread > 0 && (
                  <span className="react-unread-badge" aria-label={t("cscw.unreadAria", { count: unread })}>
                    {t("cscw.unreadCount", { count: unread })}
                  </span>
                )}
              </div>
              <p>
                {t(isPatient ? "cscw.counterpartDoctor" : "cscw.counterpartPatient")}: {counterpartName(inv)}
                {" · "}
                {t("cscw.openedAt", { date: formatDate(inv.opened_at, i18n.language) })}
              </p>
              <p>
                {t("cscw.statusLabel")}: {t(`cscw.status.${inv.status}`, { defaultValue: inv.status })}
                {" · "}
                {t("cscw.awaiting")}: {inv.awaiting_role ? t(`cscw.roles.${inv.awaiting_role}`, { defaultValue: inv.awaiting_role }) : t("cscw.nobody")}
              </p>
              <p>{inv.atypical_day_event_id ? t("cscw.originAtypical") : t("cscw.noAtypical")}</p>
              <Link to={`/investigations/${inv.id}`}>{t("cscw.openConversation")}</Link>
            </article>
          );
        })}
      </div>
    </section>
  );
}
