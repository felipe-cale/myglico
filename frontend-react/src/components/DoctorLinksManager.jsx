import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { searchDoctors, requestDoctorLink, fetchDoctorLinks, revokeDoctorLink, cancelDoctorLink, confirmDoctorLink, rejectDoctorLink } from "../api";
import StateBlock from "./StateBlock";
import ConfirmDialog from "./ConfirmDialog";
import Pagination from "./Pagination";
import { ChevronDownIcon } from "./Icons";
import { preferredScrollBehavior } from "../hooks/usePrefersReducedMotion";

const STATUS_ORDER = { active: 0, pending: 1, revoked: 2, rejected: 3, cancelled: 4 };

function formatDate(value, locale) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(parsed);
}

function DoctorTrustBadges({ doctor }) {
  const { t } = useTranslation();
  if (!doctor || (!doctor.is_demo && !(doctor.crm && !doctor.declared_verified))) return null;
  return (
    <span className="react-badges react-badges--inline">
      {doctor.is_demo && <span className="react-badge react-badge--soft react-badge--compact">{t("dashboard.demoDoctor")}</span>}
      {doctor.crm && !doctor.declared_verified && (
        <span className="react-badge react-badge--soft react-badge--compact">{t("dashboard.declaredUnverified")}</span>
      )}
    </span>
  );
}

function StatusChip({ status }) {
  const { t } = useTranslation();
  return (
    <span className={`react-status-chip react-status-chip--${status}`}>
      {t(`dashboard.status.${status}`, { defaultValue: status })}
    </span>
  );
}

function DoctorIdentity({ doctor }) {
  const { t } = useTranslation();
  return (
    <div className="react-link-card__identity">
      <strong>{doctor?.name}</strong>
      <span className="react-link-card__meta">
        {doctor?.crm ? t("dashboard.crmUfValue", { crm: doctor.crm, uf: doctor.uf }) : null}
        {doctor?.crm && doctor?.short_id ? " · " : null}
        {doctor?.short_id ? t("dashboard.doctorCode", { code: doctor.short_id }) : null}
      </span>
      <DoctorTrustBadges doctor={doctor} />
    </div>
  );
}

function useDoctorLinks({ status: statusFilter = "", page = 1, pageSize = 10 } = {}) {
  const [links, setLinks] = useState([]);
  const [status, setStatus] = useState("loading");
  const [pagination, setPagination] = useState({ page: 1, page_size: 10, total: 0, pages: 1 });
  const reload = useCallback(async () => {
    try {
      const params = { page, page_size: pageSize };
      if (statusFilter) params.status = statusFilter;
      const data = await fetchDoctorLinks(params);
      setLinks(data.links || data || []);
      if (data.pagination) setPagination(data.pagination);
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, [page, pageSize, statusFilter]);
  useEffect(() => {
    reload();
  }, [reload]);
  return { links, status, pagination, reload };
}

export default function DoctorLinksManager() {
  const { t } = useTranslation();
  const location = useLocation();
  const [criteria, setCriteria] = useState({ short_id: "", crm: "", uf: "" });
  const [searchResult, setSearchResult] = useState(null);
  const [searching, setSearching] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [searchTouched, setSearchTouched] = useState(false);
  const [error, setError] = useState("");
  const [revokeTarget, setRevokeTarget] = useState(null);
  const [revoking, setRevoking] = useState(false);
  const [revokeError, setRevokeError] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const { links, status: linksStatus, pagination, reload } = useDoctorLinks({ page, pageSize });
  const targetLookupRef = useRef("");

  useEffect(() => {
    if (pagination.page !== page) setPage(pagination.page);
  }, [pagination.page, page]);

  useEffect(() => {
    if (linksStatus === "ready" && links.length === 0 && !searchTouched) setShowSearch(true);
  }, [linksStatus, links.length, searchTouched]);

  useEffect(() => {
    if (linksStatus !== "ready" || !location.hash.startsWith("#doctor-link-")) return;
    const targetId = decodeURIComponent(location.hash.slice("#doctor-link-".length));
    if (document.getElementById(`doctor-link-${targetId}`)) {
      requestAnimationFrame(() => document.getElementById(`doctor-link-${targetId}`)?.scrollIntoView({ behavior: preferredScrollBehavior(), block: "center" }));
      return;
    }
    if (targetLookupRef.current === targetId) return;
    targetLookupRef.current = targetId;
    fetchDoctorLinks({ link_id: targetId, page_size: pageSize })
      .then((data) => { if (data.pagination?.page) setPage(data.pagination.page); })
      .catch(() => {});
  }, [linksStatus, location.hash, links, pageSize]);

  const toggleSearch = () => {
    setSearchTouched(true);
    setShowSearch((current) => !current);
    setError("");
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    setSearching(true);
    setSearchResult(null);
    setError("");
    const shortId = criteria.short_id.trim();
    const crm = criteria.crm.trim();
    const uf = criteria.uf.trim();
    if (!shortId && (!crm || !uf)) {
      setError(t("dashboard.searchCriteriaRequired"));
      setSearching(false);
      return;
    }
    try {
      const res = await searchDoctors(shortId ? { short_id: shortId } : { crm, uf });
      setSearchResult(res.doctor);
      if (!res.doctor) setError(t("dashboard.doctorNotFound"));
    } catch {
      setError(t("dashboard.searchFailed"));
    }
    setSearching(false);
  };

  const handleRequestLink = async (shortId) => {
    try {
      await requestDoctorLink(shortId);
      await reload();
      setSearchResult(null);
      setError("");
    } catch {
      setError(t("dashboard.linkActionFailed"));
    }
  };

  const handleCancel = async (link) => {
    try {
      await cancelDoctorLink(link.id, link.version);
      await reload();
      setError("");
    } catch {
      setError(t("dashboard.linkActionFailed"));
    }
  };

  const handleRevoke = async () => {
    if (!revokeTarget) return;
    setRevoking(true);
    setRevokeError("");
    try {
      await revokeDoctorLink(revokeTarget.id, { version: revokeTarget.version });
      setRevokeTarget(null);
      await reload();
    } catch {
      setRevokeError(t("dashboard.linkActionFailed"));
    }
    setRevoking(false);
  };

  const sortedLinks = [...links].sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9));
  const isCurrent = (link) => link.status === "active" || link.status === "pending";
  const currentLinks = sortedLinks.filter(isCurrent);
  const historyLinks = sortedLinks.filter((link) => !isCurrent(link));
  const historyTargeted = historyLinks.some((link) => location.hash === `#doctor-link-${link.id}`);

  const renderLink = (link) => (
    <li key={link.id} id={`doctor-link-${link.id}`} className={`react-link-card${isCurrent(link) ? "" : " is-history"}`}>
      <DoctorIdentity doctor={link.doctor} />
      <div className="react-link-card__actions">
        <StatusChip status={link.status} />
        {link.status === "pending" && (
          <button type="button" className="react-button react-button--text" onClick={() => handleCancel(link)}>
            {t("dashboard.cancel")}
          </button>
        )}
        {link.status === "active" && (
          <button
            type="button"
            className="react-button react-button--text react-button--danger-text"
            onClick={() => {
              setRevokeError("");
              setRevokeTarget(link);
            }}
          >
            {t("dashboard.revokeLink")}
          </button>
        )}
      </div>
    </li>
  );

  return (
    <section id="doctor-links" className="react-panel" aria-labelledby="my-doctors-title">
      <div className="react-panel__header">
        <div className="react-panel__header-copy">
          <h2 id="my-doctors-title">{t("dashboard.myDoctors")}</h2>
          <p>{t("dashboard.myDoctorsBody")}</p>
        </div>
        <button
          type="button"
          className={`react-button${showSearch || currentLinks.length > 0 || linksStatus !== "ready" ? " react-button--ghost" : ""}`}
          aria-expanded={showSearch}
          aria-controls="doctor-search"
          onClick={toggleSearch}
        >
          {showSearch ? t("dashboard.closeSearch") : t("dashboard.addDoctor")}
        </button>
      </div>

      {showSearch && (
        <div id="doctor-search" className="react-subpanel">
          <div className="react-subpanel__copy">
            <h3>{t("dashboard.searchDoctor")}</h3>
            <p>{t("dashboard.searchDoctorHelp")}</p>
          </div>
          <form className="react-doctor-search" onSubmit={handleSearch}>
            <label className="react-field react-doctor-search__code">
              <span>{t("dashboard.shortId")}</span>
              <input type="text" value={criteria.short_id} onChange={e => setCriteria({ ...criteria, short_id: e.target.value })} />
            </label>
            <span className="react-doctor-search__or">{t("common.or")}</span>
            <label className="react-field react-doctor-search__crm">
              <span>{t("auth.crm")}</span>
              <input type="text" value={criteria.crm} onChange={e => setCriteria({ ...criteria, crm: e.target.value })} />
            </label>
            <label className="react-field react-doctor-search__uf">
              <span>{t("auth.uf")}</span>
              <input type="text" maxLength={2} value={criteria.uf} onChange={e => setCriteria({ ...criteria, uf: e.target.value })} />
            </label>
            <button type="submit" className="react-button react-doctor-search__submit" disabled={searching}>
              {t("dashboard.search")}
            </button>
          </form>
          {searchResult && (
            <article className="react-link-card react-link-card--result">
              <DoctorIdentity doctor={searchResult} />
              <div className="react-link-card__actions">
                {searchResult.link_status === "none" ? (
                  <button type="button" className="react-button react-button--compact" onClick={() => handleRequestLink(searchResult.short_id)}>
                    {t("dashboard.requestLink")}
                  </button>
                ) : (
                  <StatusChip status={searchResult.link_status} />
                )}
              </div>
            </article>
          )}
        </div>
      )}

      {error && <p className="react-form-message is-error" role="alert">{error}</p>}

      {linksStatus === "loading" ? (
        <StateBlock title={t("dashboard.loadingLinks")} description={t("dashboard.loadingLinksDescription")} tone="info" />
      ) : linksStatus === "error" ? (
        <div role="alert">
          <StateBlock title={t("dashboard.linksLoadFailed")} tone="danger" />
        </div>
      ) : (
        <>
          {currentLinks.length === 0 ? (
            <StateBlock title={t("dashboard.noDoctors.title")} description={t("dashboard.noDoctors.description")} />
          ) : (
            <ul className="react-link-list">
              {currentLinks.map(renderLink)}
            </ul>
          )}
          {historyLinks.length > 0 && (
            <details className="react-link-history" open={historyTargeted || undefined}>
              <summary>
                <span>{t("dashboard.historyToggle", { count: historyLinks.length })}</span>
                <ChevronDownIcon />
              </summary>
              <ul className="react-link-list">
                {historyLinks.map(renderLink)}
              </ul>
            </details>
          )}
          <div className="react-panel__footer">
            <Pagination page={pagination.page} pages={pagination.pages} count={pagination.total} pageSize={pageSize} onPageChange={setPage} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />
          </div>
        </>
      )}

      <ConfirmDialog
        open={Boolean(revokeTarget)}
        title={t("dashboard.revokeDialog.titlePatient", { name: revokeTarget?.doctor?.name || "" })}
        description={t("dashboard.revokeDialog.bodyPatient", { name: revokeTarget?.doctor?.name || "" })}
        confirmLabel={t("dashboard.revokeConfirm")}
        cancelLabel={t("dashboard.keepLink")}
        busy={revoking}
        error={revokeError}
        onConfirm={handleRevoke}
        onCancel={() => setRevokeTarget(null)}
      />
    </section>
  );
}

export function PendingLinksPanel({ onChange }) {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const { links: pending, status, pagination, reload } = useDoctorLinks({ status: "pending", page, pageSize });
  const targetLookupRef = useRef("");
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    if (pagination.page !== page) setPage(pagination.page);
  }, [pagination.page, page]);

  useEffect(() => {
    if (status !== "ready" || !location.hash.startsWith("#pending-link-")) return;
    const targetId = decodeURIComponent(location.hash.slice("#pending-link-".length));
    if (document.getElementById(`pending-link-${targetId}`)) {
      requestAnimationFrame(() => document.getElementById(`pending-link-${targetId}`)?.scrollIntoView({ behavior: preferredScrollBehavior(), block: "center" }));
      return;
    }
    if (targetLookupRef.current === targetId) return;
    targetLookupRef.current = targetId;
    fetchDoctorLinks({ status: "pending", link_id: targetId, page_size: pageSize })
      .then((data) => { if (data.pagination?.page) setPage(data.pagination.page); })
      .catch(() => {});
  }, [status, location.hash, pending, pageSize]);

  const decide = async (link, action) => {
    setBusyId(link.id);
    try {
      if (action === "confirm") await confirmDoctorLink(link.id, link.version);
      else await rejectDoctorLink(link.id, link.version);
      setError("");
      await reload();
      onChange?.();
    } catch {
      setError(t("dashboard.linkActionFailed"));
    }
    setBusyId(null);
  };

  return (
    <section id="pending-links" className="react-panel react-panel--pending-links" aria-labelledby="pending-links-title">
      <div className="react-panel__header">
        <div className="react-panel__header-copy">
          <h2 id="pending-links-title">{t("doctorHome.pending.title")}</h2>
          <p>{t("doctorHome.pending.body")}</p>
        </div>
        {pagination.total > 0 ? (
          <span className="react-badge react-badge--blue react-badge--compact">{t("doctorHome.pending.count", { count: pagination.total })}</span>
        ) : null}
      </div>

      {error && <p className="react-form-message is-error" role="alert">{error}</p>}

      {status === "loading" ? (
        <StateBlock title={t("common.loading")} tone="info" />
      ) : status === "error" ? (
        <div role="alert">
          <StateBlock title={t("dashboard.linksLoadFailed")} tone="danger" />
        </div>
      ) : pending.length === 0 ? (
        <StateBlock title={t("doctorHome.pending.empty.title")} description={t("doctorHome.pending.empty.description")} />
      ) : (
        <>
          <ul className="react-link-list react-pending-list">
            {pending.map((link) => (
            <li key={link.id} id={`pending-link-${link.id}`} className="react-link-card react-pending-request">
              <div className="react-link-card__identity">
                <strong>{link.patient?.display_name}</strong>
                <span className="react-link-card__meta">
                  {link.patient?.short_id ? t("dashboard.doctorCode", { code: link.patient.short_id }) : null}
                  {link.patient?.short_id && link.requested_at ? " · " : null}
                  {link.requested_at ? t("doctorHome.pending.requestedAt", { date: formatDate(link.requested_at, i18n.language) }) : null}
                </span>
              </div>
              <div className="react-link-card__actions">
                <button
                  type="button"
                  className="react-button react-button--ghost react-button--compact"
                  disabled={busyId === link.id}
                  onClick={() => decide(link, "reject")}
                >
                  {t("dashboard.reject")}
                </button>
                <button
                  type="button"
                  className="react-button react-button--compact"
                  disabled={busyId === link.id}
                  onClick={() => decide(link, "confirm")}
                >
                  {t("dashboard.accept")}
                </button>
              </div>
            </li>
            ))}
          </ul>
          {pagination.pages > 1 ? (
            <div className="react-panel__footer">
              <Pagination page={pagination.page} pages={pagination.pages} count={pagination.total} pageSize={pageSize} onPageChange={setPage} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
