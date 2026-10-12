import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

const assetUrl = (path) => `${import.meta.env.BASE_URL}${path}`;

export default function LandingPage() {
  const { t } = useTranslation();

  return (
    <div className="react-page">
      <section className="react-hero react-hero--landing">
        <div className="react-hero__content">
          <p className="react-eyebrow">{t("landing.hero.eyebrow")}</p>
          <h1>{t("landing.hero.title")}</h1>
          <p>{t("landing.hero.body")}</p>
          <p className="react-hero__note">{t("landing.hero.badgeControl")}</p>
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
          <img
            src={assetUrl("img/myglico-logo.png")}
            alt={t("overview.hero.imageAlt")}
            width="1536"
            height="1024"
            loading="lazy"
          />
        </div>
      </section>

      <section className="react-audiences">
        {["patient", "doctor"].map((audience) => (
          <div key={audience} className="react-audiences__block">
            <h2>{t(`landing.${audience}.title`)}</h2>
            <p>{t(`landing.${audience}.body`)}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
