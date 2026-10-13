import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { cancelPendingRequests, pendingRequests, subscribeLoading } from "../loadingStore";

// Fast responses never flash the overlay; once shown it stays long enough to read.
const SHOW_DELAY_MS = 300;
const MIN_VISIBLE_MS = 450;
// A slow request offers a way out instead of holding the page indefinitely.
const CANCEL_AFTER_MS = 8000;

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
  const [cancellable, setCancellable] = useState(false);
  const shownAt = useRef(0);
  const triggerRef = useRef(null);
  const overlayRef = useRef(null);
  const liveRef = useRef(null);

  useEffect(() => {
    if (pending > 0 && !visible) {
      const timer = setTimeout(() => {
        shownAt.current = Date.now();
        triggerRef.current = document.activeElement;
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
    if (!visible) {
      setCancellable(false);
      return undefined;
    }
    const timer = setTimeout(() => setCancellable(true), CANCEL_AFTER_MS);
    return () => clearTimeout(timer);
  }, [visible]);

  useEffect(() => {
    if (!visible) return undefined;
    const root = document.getElementById("root");
    root?.setAttribute("aria-busy", "true");
    // inert keeps pointer, focus and assistive tech out of the page (#root and portaled dialogs)
    // while the overlay and the live region, siblings in <body>, stay usable.
    const blocked = Array.from(document.body.children).filter((element) =>
      element !== overlayRef.current && element !== liveRef.current
      && !element.hasAttribute("inert") && !["SCRIPT", "STYLE", "TEMPLATE"].includes(element.tagName));
    blocked.forEach((element) => element.setAttribute("inert", ""));
    // App shortcuts (Escape closing dialogs, focus traps eating Tab) must not act on an inert page;
    // stopPropagation leaves every browser key (reload, address bar, close tab) untouched.
    const isolateKeys = (event) => {
      if (!overlayRef.current?.contains(event.target)) event.stopPropagation();
    };
    window.addEventListener("keydown", isolateKeys, true);
    return () => {
      blocked.forEach((element) => element.removeAttribute("inert"));
      root?.removeAttribute("aria-busy");
      window.removeEventListener("keydown", isolateKeys, true);
      const trigger = triggerRef.current;
      triggerRef.current = null;
      const focusLost = !document.activeElement || document.activeElement === document.body;
      if (!focusLost) return;
      if (trigger && trigger !== document.body && trigger.isConnected && typeof trigger.focus === "function") {
        trigger.focus({ preventScroll: true });
        return;
      }
      // The trigger was replaced (e.g. by an error state): land on that state's recovery action.
      requestAnimationFrame(() => {
        if (document.activeElement && document.activeElement !== document.body) return;
        document.querySelector("#root [role='alert'] button")?.focus({ preventScroll: true });
      });
    };
  }, [visible]);

  const handleCancel = () => {
    cancelPendingRequests();
  };

  return createPortal(
    <>
      <div ref={liveRef} className="react-visually-hidden" role="status" aria-live="polite" data-testid="global-loading-status">
        {visible ? t("common.working") : ""}
      </div>
      {visible ? (
        <div ref={overlayRef} className="react-loading" data-testid="global-loading">
          <div className="react-loading__card">
            <GlucometerAnimation />
            <p aria-hidden="true">{t("common.working")}</p>
            {cancellable ? (
              <button type="button" className="react-button react-button--ghost react-loading__cancel" onClick={handleCancel}>
                {t("common.cancelWaiting")}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </>,
    document.body
  );
}
