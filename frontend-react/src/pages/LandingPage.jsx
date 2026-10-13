import { useTranslation } from "react-i18next";
import useDocumentTitle from "../hooks/useDocumentTitle";
import { Link } from "react-router-dom";

const assetUrl = (path) => `${import.meta.env.BASE_URL}${path}`;
// Phones hide the hero visual (styles.css, max-width: 640px), so they get a 1px placeholder instead of the image.
const BLANK_PIXEL = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";

export default function LandingPage() {
  const { t } = useTranslation();
  useDocumentTitle(null);

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
          <picture>
            <source media="(max-width: 640px)" srcSet={BLANK_PIXEL} />
            <source
              type="image/webp"
              srcSet={`${assetUrl("img/myglico-logo-640.webp")} 640w, ${assetUrl("img/myglico-logo-1000.webp")} 1000w`}
              sizes="(max-width: 899px) 92vw, 560px"
            />
            <img
              src={assetUrl("img/myglico-logo.png")}
              alt={t("overview.hero.imageAlt")}
              width="1536"
              height="1024"
              loading="eager"
              fetchpriority="high"
              decoding="async"
            />
          </picture>
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
