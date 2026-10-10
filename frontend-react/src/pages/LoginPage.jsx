import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { login } from "../api";
import { useAuth } from "../contexts/AuthContext";

export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { refreshSession } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await login(email, password);
      await refreshSession();
      navigate("/dashboard");
    } catch (err) {
      setError(t("auth.error"));
    }
  };

  return (
    <div className="react-page" style={{ maxWidth: '400px', margin: '40px auto' }}>
      <h2>{t("auth.login")}</h2>
      {error && <div role="alert" style={{ color: 'red', marginBottom: '1rem' }}>{error}</div>}
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <label className="react-select-field">
          <span>{t("auth.email")}</span>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} required />
        </label>
        <label className="react-select-field">
          <span>{t("auth.password")}</span>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} required />
        </label>
        <button type="submit" style={{ padding: '10px', background: '#005fcc', color: '#fff', border: 'none', borderRadius: '4px' }}>
          {t("auth.submitLogin")}
        </button>
      </form>
    </div>
  );
}
