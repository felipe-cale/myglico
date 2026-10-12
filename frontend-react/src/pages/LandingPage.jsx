import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

const assetUrl = (path) => `${import.meta.env.BASE_URL}${path}`;

export default function LandingPage() {
  const { t } = useTranslation();

  return (
    <div className="react-page">
      <section className="react-hero">
        <div className="react-hero__content">
          <p className="react-eyebrow">{t("landing.hero.eyebrow")}</p>
          <h1>{t("landing.hero.title")}</h1>
          <p>{t("landing.hero.body")}</p>
          <div className="react-badges react-badges--overview">
            <span className="react-badge react-badge--brand">{t("landing.hero.badgeControl")}</span>
            <span className="react-badge react-badge--green">{t("landing.hero.badgePatient")}</span>
            <span className="react-badge react-badge--blue">{t("landing.hero.badgeDoctor")}</span>
          </div>
          <div className="react-actions react-hero__actions">
            <Link to="/register" className="react-button">
              {t("auth.register")}
            </Link>
            <Link to="/login" className="react-button react-button--ghost">
              {t("auth.login")}
            </Link>
          </div>
        </div>
        <div className="react-hero__visual">
          <img src={assetUrl("img/myglico-logo.png")} alt={t("overview.hero.imageAlt")} />
        </div>
      </section>

      <section className="react-grid react-grid--detail">
        {["patient", "doctor"].map((audience) => (
          <article key={audience} className="react-panel">
            <div className="react-panel__header">
              <div className="react-panel__header-copy">
                <p className="react-eyebrow">{t(`landing.${audience}.eyebrow`)}</p>
                <h2>{t(`landing.${audience}.title`)}</h2>
                <p>{t(`landing.${audience}.body`)}</p>
              </div>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
