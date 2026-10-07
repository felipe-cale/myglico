import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

const assetUrl = (path) => `${import.meta.env.BASE_URL}${path}`;

export default function LandingPage() {
  const { t } = useTranslation();

  return (
    <div className="react-page">
      <section className="react-hero">
        <div className="react-hero__content">
          <h1>{t("overview.hero.title")}</h1>
          <p>{t("overview.hero.body")}</p>
          <div className="react-badges react-badges--overview">
            <span className="react-badge react-badge--brand">{t("overview.hero.badgeDaily")}</span>
            <span className="react-badge react-badge--green">{t("overview.hero.badgeClinical")}</span>
            <span className="react-badge react-badge--blue">{t("overview.hero.badgeContinuous")}</span>
          </div>
          <div style={{ marginTop: '2rem', display: 'flex', gap: '1rem' }}>
            <Link to="/login" className="react-button" style={{ background: '#005fcc', color: '#fff', padding: '10px 20px', borderRadius: '4px', textDecoration: 'none' }}>
              {t("auth.login")}
            </Link>
            <Link to="/register" className="react-button" style={{ border: '1px solid #005fcc', color: '#005fcc', padding: '10px 20px', borderRadius: '4px', textDecoration: 'none' }}>
              {t("auth.register")}
            </Link>
          </div>
        </div>
        <div className="react-hero__visual">
          <img src={assetUrl("img/myglico-logo.png")} alt={t("overview.hero.imageAlt")} />
        </div>
      </section>
    </div>
  );
}
