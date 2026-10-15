import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { cancelPendingRequests, pendingRequests, subscribeLoading } from "../loadingStore";

// Fast responses never flash the overlay; once shown it stays long enough to read.
const SHOW_DELAY_MS = 300;
const MIN_VISIBLE_MS = 450;
// A slow request offers a way out instead of holding the page indefinitely.
const CANCEL_AFTER_MS = 8000;

const MASCOT_SRC = `${import.meta.env.BASE_URL}img/mascote-avatar-192.webp`;

// Warm the cache as soon as the app loads, so the mascot is there before the first overlay needs it.
if (typeof Image !== "undefined") {
  const preload = new Image();
  preload.src = MASCOT_SRC;
}

function GlucometerAnimation() {
  const base = import.meta.env.BASE_URL;
  const [ready, setReady] = useState(false);
  const imageRef = useRef(null);

  useEffect(() => {
    if (imageRef.current?.complete) setReady(true);
  }, []);

  // The drop only starts falling once the mascot is on screen: it lands on the strip, never alone.
  return (
    <div className={`react-loading__art${ready ? " is-ready" : ""}`} aria-hidden="true">
      <svg className="react-loading__drop-art" viewBox="0 0 24 32" focusable="false">
        <path className="react-loading__drop" d="M12 2c-4 6-7 10-7 14a7 7 0 0 0 14 0c0-4-3-8-7-14z" />
      </svg>
      <img
        ref={imageRef}
        className="react-loading__mascot"
        src={MASCOT_SRC}
        srcSet={`${base}img/mascote-avatar-192.webp 1x, ${base}img/mascote-avatar-420.webp 2x`}
        alt=""
        width="112"
        height="112"
        onLoad={() => setReady(true)}
      />
      <span className="react-loading__shadow" />
    </div>
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

  // Blocking ends the moment the last request settles; only the short fade-out keeps the veil on screen,
  // so typing right after the content appears is never swallowed by an inert page.
  const blocking = visible && pending > 0;

  useEffect(() => {
    if (!blocking) return undefined;
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
  }, [blocking]);

  const handleCancel = () => {
    cancelPendingRequests();
  };

  return createPortal(
    <>
      <div ref={liveRef} className="react-visually-hidden" role="status" aria-live="polite" data-testid="global-loading-status">
        {visible ? t("common.working") : ""}
      </div>
      {visible ? (
        <div ref={overlayRef} className={`react-loading${blocking ? "" : " is-releasing"}`} data-testid="global-loading">
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
