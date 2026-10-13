import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { pendingRequests, subscribeLoading } from "../loadingStore";

// Fast responses never flash the overlay; once shown it stays long enough to read.
const SHOW_DELAY_MS = 300;
const MIN_VISIBLE_MS = 450;

function GlucometerAnimation() {
  return (
    <svg className="react-loading__art" viewBox="0 0 120 120" aria-hidden="true" focusable="false">
      <path className="react-loading__drop" d="M60 6c-6 9-11 15-11 21a11 11 0 0 0 22 0c0-6-5-12-11-21z" />
      <rect className="react-loading__strip" x="52" y="40" width="16" height="22" rx="3" />
      <rect className="react-loading__meter" x="26" y="56" width="68" height="58" rx="18" />
      <rect className="react-loading__screen" x="38" y="68" width="44" height="24" rx="7" />
      <g className="react-loading__digits">
        <circle cx="50" cy="80" r="3" />
        <circle cx="60" cy="80" r="3" />
        <circle cx="70" cy="80" r="3" />
      </g>
      <circle className="react-loading__button" cx="60" cy="103" r="4" />
    </svg>
  );
}

export default function GlobalLoading() {
  const { t } = useTranslation();
  const pending = useSyncExternalStore(subscribeLoading, pendingRequests);
  const [visible, setVisible] = useState(false);
  const shownAt = useRef(0);

  useEffect(() => {
    if (pending > 0 && !visible) {
      const timer = setTimeout(() => {
        shownAt.current = Date.now();
        setVisible(true);
      }, SHOW_DELAY_MS);
      return () => clearTimeout(timer);
    }
    if (pending === 0 && visible) {
      const remaining = Math.max(0, MIN_VISIBLE_MS - (Date.now() - shownAt.current));
      const timer = setTimeout(() => setVisible(false), remaining);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [pending, visible]);

  useEffect(() => {
    if (!visible) return undefined;
    const root = document.getElementById("root");
    root?.setAttribute("aria-busy", "true");
    // Keys must not reach the page while it is blocked.
    const blockKeys = (event) => {
      event.preventDefault();
      event.stopPropagation();
    };
    window.addEventListener("keydown", blockKeys, true);
    return () => {
      root?.removeAttribute("aria-busy");
      window.removeEventListener("keydown", blockKeys, true);
    };
  }, [visible]);

  if (!visible) return null;

  return createPortal(
    <div className="react-loading" role="status" aria-live="polite" data-testid="global-loading">
      <div className="react-loading__card">
        <GlucometerAnimation />
        <p>{t("common.working")}</p>
      </div>
    </div>,
    document.body
  );
}
