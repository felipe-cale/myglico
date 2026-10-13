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
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

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
      <section className="react-panel react-auth__card react-auth__card--register">
        <div className="react-panel__header">
          <div className="react-panel__header-copy">
            <h1>{t("auth.register")}</h1>
            <p>{t("auth.registerBody")}</p>
          </div>
        </div>
        {error && <p className="react-form-message is-error" role="alert">{error}</p>}
        <form className="react-form react-register-form" onSubmit={handleSubmit}>
          <label className="react-select-field react-register-form__role">
            <span>{t("auth.role")}</span>
            <select value={role} onChange={e => setRole(e.target.value)}>
              <option value="patient">{t("auth.rolePatient")}</option>
              <option value="doctor">{t("auth.roleDoctor")}</option>
            </select>
          </label>

          <label className="react-field react-register-form__name">
            <span>{role === "doctor" ? t("auth.docName") : t("auth.name")}</span>
            <input type="text" autoComplete="name" value={displayName} onChange={e => setDisplayName(e.target.value)} required />
          </label>

          {role === "doctor" && (
            <div className="react-form__row react-form__row--crm react-register-form__crm">
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

          <label className="react-field react-register-form__email">
            <span>{t("auth.email")}</span>
            <input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required />
          </label>

          <div className="react-form__row react-register-form__passwords">
            <label className="react-field">
              <span>{t("auth.password")}</span>
              <div className="react-password-input">
                <input type={showPassword ? "text" : "password"} autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} minLength={8} required />
                <button
                  type="button"
                  className="react-password-input__toggle"
                  onClick={() => setShowPassword(value => !value)}
                  aria-label={t(showPassword ? "auth.hidePassword" : "auth.showPassword")}
                  aria-pressed={showPassword}
                >
                  <PasswordVisibilityIcon visible={showPassword} />
                  <span>{t(showPassword ? "auth.hidePassword" : "auth.showPassword")}</span>
                </button>
              </div>
            </label>
            <label className="react-field">
              <span>{t("auth.passwordConfirm")}</span>
              <div className="react-password-input">
                <input type={showConfirmPassword ? "text" : "password"} autoComplete="new-password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} minLength={8} required />
                <button
                  type="button"
                  className="react-password-input__toggle"
                  onClick={() => setShowConfirmPassword(value => !value)}
                  aria-label={t(showConfirmPassword ? "auth.hidePassword" : "auth.showPassword")}
                  aria-pressed={showConfirmPassword}
                >
                  <PasswordVisibilityIcon visible={showConfirmPassword} />
                  <span>{t(showConfirmPassword ? "auth.hidePassword" : "auth.showPassword")}</span>
                </button>
              </div>
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
                aria-required="true"
              />
              <span>{t("auth.privacyAccept")}</span>
            </label>
          </div>

          <button type="submit" className="react-button react-button--block" disabled={submitting} aria-busy={submitting}>
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

function PasswordVisibilityIcon({ visible }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      {visible ? (
        <>
          <path d="M3 3l18 18" />
          <path d="M10.6 10.6a2 2 0 002.8 2.8" />
          <path d="M9.9 5.2A10.8 10.8 0 0112 5c5.2 0 8.8 4.6 9.7 6-.4.7-1.5 2.2-3.2 3.6M6.2 6.2C3.9 7.6 2.6 9.7 2.3 11c.9 1.4 4.5 6 9.7 6 1 0 1.9-.2 2.8-.5" />
        </>
      ) : (
        <>
          <path d="M2.3 12S5.8 6 12 6s9.7 6 9.7 6-3.5 6-9.7 6-9.7-6-9.7-6z" />
          <circle cx="12" cy="12" r="2.5" />
        </>
      )}
    </svg>
  );
}
