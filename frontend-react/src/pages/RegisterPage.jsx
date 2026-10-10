import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { registerAccount } from "../api";
import { useAuth } from "../contexts/AuthContext";

export default function RegisterPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { refreshSession } = useAuth();

  const [role, setRole] = useState("patient");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [displayName, setDisplayName] = useState("");
  const [crm, setCrm] = useState("");
  const [uf, setUf] = useState("");
  const [privacyAccepted, setPrivacyAccepted] = useState(false);

  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError(t("auth.passwordMismatch"));
      return;
    }
    if (role === "doctor" && (!crm.trim() || !uf.trim())) {
      setError(t("auth.crmUfRequired"));
      return;
    }
    if (!privacyAccepted) {
      setError(t("auth.privacyRequired"));
      return;
    }
    try {
      const payload = {
        role,
        email,
        password,
        password_confirmation: confirmPassword,
        display_name: displayName,
        privacy_notice_accepted: privacyAccepted,
        ...(role === "doctor" ? { crm: crm.trim(), uf: uf.trim().toUpperCase() } : {})
      };
      await registerAccount(payload);
      await refreshSession();
      navigate("/dashboard");
    } catch (err) {
      setError(t("auth.error"));
    }
  };

  return (
    <div className="react-page" style={{ maxWidth: '400px', margin: '40px auto' }}>
      <h2>{t("auth.register")}</h2>
      {error && <div role="alert" style={{ color: 'red', marginBottom: '1rem' }}>{error}</div>}
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <label className="react-select-field">
          <span>{t("auth.role")}</span>
          <select value={role} onChange={e => setRole(e.target.value)}>
            <option value="patient">{t("auth.rolePatient")}</option>
            <option value="doctor">{t("auth.roleDoctor")}</option>
          </select>
        </label>

        <label className="react-select-field">
          <span>{t("auth.email")}</span>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} required />
        </label>

        <label className="react-select-field">
          <span>{t("auth.password")}</span>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} minLength={8} required />
        </label>

        <label className="react-select-field">
          <span>{t("auth.passwordConfirm")}</span>
          <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} minLength={8} required />
        </label>

        {role === "patient" && (
          <label className="react-select-field">
            <span>{t("auth.name")}</span>
            <input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)} required />
          </label>
        )}

        {role === "doctor" && (
          <>
            <label className="react-select-field">
              <span>{t("auth.docName")}</span>
              <input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)} required />
            </label>
            <label className="react-select-field">
              <span>{t("auth.crm")}</span>
              <input type="text" value={crm} onChange={e => setCrm(e.target.value)} required />
            </label>
            <label className="react-select-field">
              <span>{t("auth.uf")}</span>
              <input type="text" value={uf} onChange={e => setUf(e.target.value)} maxLength={2} required />
            </label>
          </>
        )}

        <div className="react-privacy-notice">
          <p id="privacy-notice-text">{t("auth.privacyNotice")}</p>
          <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
            <input
              type="checkbox"
              checked={privacyAccepted}
              onChange={e => setPrivacyAccepted(e.target.checked)}
              aria-describedby="privacy-notice-text"
              required
            />
            <span>{t("auth.privacyAccept")}</span>
          </label>
        </div>

        <button type="submit" disabled={!privacyAccepted} style={{ padding: '10px', background: '#005fcc', color: '#fff', border: 'none', borderRadius: '4px' }}>
          {t("auth.submitRegister")}
        </button>
      </form>
    </div>
  );
}
