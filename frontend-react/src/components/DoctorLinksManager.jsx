import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { searchDoctors, requestDoctorLink, fetchDoctorLinks, revokeDoctorLink, cancelDoctorLink, confirmDoctorLink, rejectDoctorLink } from "../api";
import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

function DoctorTrustBadges({ doctor }) {
  const { t } = useTranslation();
  if (!doctor) return null;
  return (
    <span className="react-badges">
      {doctor.is_demo && <span className="react-badge react-badge--soft">{t("dashboard.demoDoctor")}</span>}
      {doctor.crm && !doctor.declared_verified && (
        <span className="react-badge react-badge--soft">{t("dashboard.declaredUnverified")}</span>
      )}
    </span>
  );
}

export default function DoctorLinksManager() {
  const { t } = useTranslation();
  const { session } = useAuth();
  
  const [links, setLinks] = useState([]);
  const [searchParams, setSearchParams] = useState({ short_id: "", crm: "", uf: "" });
  const [searchResult, setSearchResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [linksStatus, setLinksStatus] = useState("loading");

  const loadLinks = async () => {
    try {
      const data = await fetchDoctorLinks();
      setLinks(data.links || data || []);
      setLinksStatus("ready");
    } catch(e) {
      setLinksStatus("error");
    }
  };

  useEffect(() => {
    loadLinks();
  }, []);

  const handleSearch = async (e) => {
    e.preventDefault();
    setLoading(true);
    setSearchResult(null);
    setError("");
    const shortId = searchParams.short_id.trim();
    const crm = searchParams.crm.trim();
    const uf = searchParams.uf.trim();
    if (!shortId && (!crm || !uf)) {
      setError(t("dashboard.searchCriteriaRequired"));
      setLoading(false);
      return;
    }
    try {
      const res = await searchDoctors(shortId ? { short_id: shortId } : { crm, uf });
      setSearchResult(res.doctor);
      if (!res.doctor) setError(t("dashboard.doctorNotFound"));
    } catch(e) {
      setError(t("dashboard.searchFailed"));
    }
    setLoading(false);
  };

  const handleRequestLink = async (short_id) => {
    try {
      await requestDoctorLink(short_id);
      loadLinks();
      setSearchResult(null);
      setError("");
    } catch(e) { setError(t("dashboard.linkActionFailed")); }
  };

  const handleAction = async (action, id, version) => {
    try {
      if (action === 'revoke') await revokeDoctorLink(id, { version });
      if (action === 'cancel') await cancelDoctorLink(id);
      if (action === 'confirm') await confirmDoctorLink(id, version);
      if (action === 'reject') await rejectDoctorLink(id, version);
      loadLinks();
      setError("");
    } catch(e) { setError(t("dashboard.linkActionFailed")); }
  };

  const isPatient = session?.account?.roles?.includes('patient');
  const activeLinks = links.filter((link) => link.status === "active");
  const listedLinks = isPatient ? links : links.filter((link) => link.status !== "active");

  return (
    <div style={{ marginTop: '2rem' }}>
      <h3>{isPatient ? t("dashboard.myDoctors") : t("dashboard.myLinks")}</h3>
      
      {isPatient && (
        <div style={{ background: '#f9f9f9', padding: '1rem', marginBottom: '1rem', borderRadius: '4px' }}>
          <h4>{t("dashboard.searchDoctor")}</h4>
          <form onSubmit={handleSearch} style={{ display: 'flex', gap: '1rem', alignItems: 'end', flexWrap: 'wrap' }}>
            <label className="react-select-field">
              <span>{t("dashboard.shortId")}</span>
              <input type="text" value={searchParams.short_id} onChange={e => setSearchParams({...searchParams, short_id: e.target.value})} />
            </label>
            <span style={{ paddingBottom: '10px' }}>{t("common.or")}</span>
            <label className="react-select-field">
              <span>{t("auth.crm")}</span>
              <input type="text" value={searchParams.crm} onChange={e => setSearchParams({...searchParams, crm: e.target.value})} />
            </label>
            <label className="react-select-field">
              <span>{t("auth.uf")}</span>
              <input type="text" value={searchParams.uf} onChange={e => setSearchParams({...searchParams, uf: e.target.value})} />
            </label>
            <button type="submit" disabled={loading} style={{ padding: '10px', background: '#005fcc', color: '#fff', border: 'none', borderRadius: '4px' }}>
              {t("dashboard.search")}
            </button>
          </form>
          {searchResult && (
            <div style={{ marginTop: '1rem', padding: '1rem', border: '1px solid #ccc', borderRadius: '4px' }}>
              <p><strong>{searchResult.name}</strong> ({searchResult.short_id})</p>
              {searchResult.crm && <p>{t("dashboard.crmUfValue", { crm: searchResult.crm, uf: searchResult.uf })}</p>}
              <DoctorTrustBadges doctor={searchResult} />
              {searchResult.link_status === "none" ? (
                <button onClick={() => handleRequestLink(searchResult.short_id)} style={{ padding: '8px', background: '#28a745', color: '#fff', border: 'none', borderRadius: '4px' }}>
                  {t("dashboard.requestLink")}
                </button>
              ) : (
                <p>{t("dashboard.statusLabel")}: {t(`dashboard.status.${searchResult.link_status}`, { defaultValue: searchResult.link_status })}</p>
              )}
            </div>
          )}
        </div>
      )}
      {error && <p role="alert">{error}</p>}

      {!isPatient && (
        <section className="react-my-patients" aria-labelledby="my-patients-title">
          <h4 id="my-patients-title">{t("dashboard.myPatients")}</h4>
          {linksStatus === "loading" ? (
            <p role="status">{t("common.loading")}</p>
          ) : activeLinks.length === 0 ? (
            <p>{t("dashboard.noPatients")}</p>
          ) : (
            <ul className="react-my-patients__list">
              {activeLinks.map((link) => (
                <li key={link.id} className="react-my-patients__item">
                  <span>
                    <strong>{link.patient?.display_name}</strong>
                    {link.patient?.short_id && <small> ({link.patient.short_id})</small>}
                  </span>
                  <Link to={`/patients/${link.patient_id}`} className="react-button">
                    {t("dashboard.openPatientDetail")}
                  </Link>
                  <button type="button" onClick={() => handleAction('revoke', link.id, link.version)}>{t("dashboard.revokeLink")}</button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {!isPatient && <h4>{t("dashboard.linkRequests")}</h4>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {linksStatus === "error" ? <p role="alert">{t("dashboard.linksLoadFailed")}</p> : listedLinks.length === 0 ? <p>{t("dashboard.noLinks")}</p> : listedLinks.map(link => (
          <div key={link.id} style={{ border: '1px solid #ddd', padding: '1rem', borderRadius: '4px' }}>
            <p><strong>{t("dashboard.statusLabel")}:</strong> {t(`dashboard.status.${link.status}`, { defaultValue: link.status })}</p>
            {isPatient ? (
               <>
                 <p><strong>{t("dashboard.doctorLabel")}:</strong> {link.doctor?.name}</p>
                 <DoctorTrustBadges doctor={link.doctor} />
               </>
            ) : (
               <p><strong>{t("dashboard.patientLabel")}:</strong> {link.patient?.display_name}</p>
            )}
            <div style={{ marginTop: '10px', display: 'flex', gap: '10px' }}>
              {link.status === 'pending' && isPatient && (
                <button onClick={() => handleAction('cancel', link.id, link.version)}>{t("dashboard.cancel")}</button>
              )}
              {link.status === 'pending' && !isPatient && (
                <>
                  <button onClick={() => handleAction('confirm', link.id, link.version)}>{t("dashboard.accept")}</button>
                  <button onClick={() => handleAction('reject', link.id, link.version)}>{t("dashboard.reject")}</button>
                </>
              )}
              {link.status === 'active' && (
                <button onClick={() => handleAction('revoke', link.id, link.version)}>{t("dashboard.revokeLink")}</button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
