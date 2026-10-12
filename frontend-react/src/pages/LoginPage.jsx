import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { login } from "../api";
import { useAuth } from "../contexts/AuthContext";

export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { refreshSession } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
      setError(t("auth.error"));
      setSubmitting(false);
    }
  };

  return (
    <div className="react-page react-auth">
      <section className="react-panel react-auth__card">
        <div className="react-panel__header">
          <div className="react-panel__header-copy">
            <p className="react-eyebrow">{t("auth.loginEyebrow")}</p>
            <h2>{t("auth.login")}</h2>
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
            <input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required />
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
