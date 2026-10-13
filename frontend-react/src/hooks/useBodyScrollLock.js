import { useEffect } from "react";

// Shared across every open dialog/drawer so nested or overlapping ones restore the page only once.
let locks = 0;
let saved = null;

export default function useBodyScrollLock(active) {
  useEffect(() => {
    if (!active || typeof document === "undefined") return undefined;
    const { body, documentElement } = document;
    if (locks === 0) {
      const scrollbarWidth = window.innerWidth - documentElement.clientWidth;
      saved = { overflow: body.style.overflow, paddingRight: body.style.paddingRight };
      body.style.overflow = "hidden";
      // Keeps the layout from shifting when the scrollbar disappears.
      if (scrollbarWidth > 0) body.style.paddingRight = `${scrollbarWidth}px`;
    }
    locks += 1;
    return () => {
      locks = Math.max(0, locks - 1);
      if (locks === 0 && saved) {
        body.style.overflow = saved.overflow;
        body.style.paddingRight = saved.paddingRight;
        saved = null;
      }
    };
  }, [active]);
}
