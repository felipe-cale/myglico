import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
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
  const [submitting, setSubmitting] = useState(false);

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
    setSubmitting(true);
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
      setSubmitting(false);
    }
  };

  return (
    <div className="react-page react-auth">
      <section className="react-panel react-auth__card react-auth__card--wide">
        <div className="react-panel__header">
          <div className="react-panel__header-copy">
            <p className="react-eyebrow">{t("auth.registerEyebrow")}</p>
            <h2>{t("auth.register")}</h2>
            <p>{t("auth.registerBody")}</p>
          </div>
        </div>
        {error && <p className="react-form-message is-error" role="alert">{error}</p>}
        <form className="react-form" onSubmit={handleSubmit}>
          <label className="react-select-field">
            <span>{t("auth.role")}</span>
            <select value={role} onChange={e => setRole(e.target.value)}>
              <option value="patient">{t("auth.rolePatient")}</option>
              <option value="doctor">{t("auth.roleDoctor")}</option>
            </select>
          </label>

          <label className="react-field">
            <span>{role === "doctor" ? t("auth.docName") : t("auth.name")}</span>
            <input type="text" autoComplete="name" value={displayName} onChange={e => setDisplayName(e.target.value)} required />
          </label>

          {role === "doctor" && (
            <div className="react-form__row react-form__row--crm">
              <label className="react-field">
                <span>{t("auth.crm")}</span>
                <input type="text" inputMode="numeric" value={crm} onChange={e => setCrm(e.target.value)} required />
              </label>
              <label className="react-field">
                <span>{t("auth.uf")}</span>
                <input type="text" value={uf} onChange={e => setUf(e.target.value)} maxLength={2} required />
              </label>
            </div>
          )}

          <label className="react-field">
            <span>{t("auth.email")}</span>
            <input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required />
          </label>

          <div className="react-form__row">
            <label className="react-field">
              <span>{t("auth.password")}</span>
              <input type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} minLength={8} required />
            </label>
            <label className="react-field">
              <span>{t("auth.passwordConfirm")}</span>
              <input type="password" autoComplete="new-password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} minLength={8} required />
            </label>
          </div>

          <div className="react-privacy-notice">
            <p id="privacy-notice-text">{t("auth.privacyNotice")}</p>
            <label className="react-check">
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

          <button type="submit" className="react-button react-button--block" disabled={!privacyAccepted || submitting}>
            {t("auth.submitRegister")}
          </button>
        </form>
        <p className="react-auth__switch">
          {t("auth.haveAccount")} <Link to="/login">{t("auth.login")}</Link>
        </p>
      </section>
    </div>
  );
}
