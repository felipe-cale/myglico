import { useEffect, useRef } from "react";

// Polls only while the tab is visible and refreshes as soon as it becomes visible again.
export default function useVisibleInterval(callback, delay, enabled = true) {
  const savedCallback = useRef(callback);
  savedCallback.current = callback;

  useEffect(() => {
    if (!enabled || typeof document === "undefined") return undefined;
    let timer = null;
    const tick = () => savedCallback.current();
    const start = () => {
      if (timer === null) timer = setInterval(tick, delay);
    };
    const stop = () => {
      if (timer !== null) clearInterval(timer);
      timer = null;
    };
    const handleVisibility = () => {
      if (document.visibilityState === "hidden") {
        stop();
      } else {
        tick();
        start();
      }
    };
    if (document.visibilityState !== "hidden") start();
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [delay, enabled]);
}
