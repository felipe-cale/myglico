import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import useDocumentTitle from "../hooks/useDocumentTitle";
import { useAuth } from "../contexts/AuthContext";

const assetUrl = (path) => `${import.meta.env.BASE_URL}${path}`;

// Shown for anything unexpected (a Glico call that failed in a way we do not handle, or a crash while rendering).
// It lives at /erro so it can be linked, redirected to and previewed; ?origem=glico adds a hint about unsaved readings.
export default function ErrorPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const { session } = useAuth();
  useDocumentTitle(t("errorPage.documentTitle"));

  const fromGlico = params.get("origem") === "glico";
  const home = session?.authenticated ? "/dashboard" : "/";

  return (
    <div className="react-page error-page">
      <img
        className="error-page__mascot"
        src={assetUrl("img/mascote-erro-480.webp")}
        srcSet={`${assetUrl("img/mascote-erro-240.webp")} 240w, ${assetUrl("img/mascote-erro-480.webp")} 480w`}
        sizes="(max-width: 600px) 200px, 240px"
        alt={t("errorPage.imageAlt")}
        width="240"
        height="240"
      />
      <h1>{t("errorPage.title")}</h1>
      <p className="error-page__body">{t(fromGlico ? "errorPage.bodyGlico" : "errorPage.body")}</p>
      <div className="error-page__actions">
        <Link to={home} className="lp-button lp-button--primary">
          {t("errorPage.home")}
        </Link>
      </div>
    </div>
  );
}
