import { useState } from "react";
import { useTranslation } from "react-i18next";
import useDocumentTitle from "../hooks/useDocumentTitle";
import { Link, useNavigate } from "react-router-dom";
import { login } from "../api";
import { useAuth } from "../contexts/AuthContext";
import PasswordVisibilityIcon from "../components/PasswordVisibilityIcon";

export default function LoginPage() {
  const { t } = useTranslation();
  useDocumentTitle(t("documentTitle.login"));
  const navigate = useNavigate();
  const { refreshSession } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await login(email, password);
      await refreshSession();
      navigate("/dashboard");
    } catch (err) {
      // A timeout or a cancel from the loading overlay says nothing about the credentials.
      setError(t(err?.code === "timeout" || err?.code === "aborted" ? "common.requestStopped" : "auth.error"));
      setSubmitting(false);
    }
  };

  return (
    <div className="react-page react-auth">
      <section className="react-panel react-auth__card">
        <img className="react-auth__mascot" src={`${import.meta.env.BASE_URL}img/mascote-avatar-192.webp`} alt="" width="72" height="72" />
        <div className="react-panel__header">
          <div className="react-panel__header-copy">
            <h1>{t("auth.login")}</h1>
            <p>{t("auth.loginBody")}</p>
          </div>
        </div>
        {error && <p className="react-form-message is-error" role="alert">{error}</p>}
        <form className="react-form" onSubmit={handleSubmit}>
          <label className="react-field">
            <span>{t("auth.email")}</span>
            <input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required />
          </label>
          <label className="react-field">
            <span>{t("auth.password")}</span>
            <div className="react-password-input">
              <input type={showPassword ? "text" : "password"} autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required />
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
          <button type="submit" className="react-button react-button--block" disabled={submitting}>
            {t("auth.submitLogin")}
          </button>
        </form>
        <p className="react-auth__switch">
          {t("auth.noAccount")} <Link to="/register">{t("auth.register")}</Link>
        </p>
      </section>
    </div>
  );
}
