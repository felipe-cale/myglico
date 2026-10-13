import { useEffect } from "react";
import { useTranslation } from "react-i18next";

// "{{page}} · MyGlico"; without a page name the tab shows just the product name.
export default function useDocumentTitle(page) {
  const { t, i18n } = useTranslation();
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.title = page ? t("documentTitle.format", { page }) : "MyGlico";
  }, [page, t, i18n.language]);
}
