import { useEffect, useRef } from "react";

export const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type=\"hidden\"])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "summary",
  "[tabindex]:not([tabindex=\"-1\"])"
].join(", ");

function focusableIn(container) {
  return Array.from(container.querySelectorAll(FOCUSABLE)).filter((element) => element.getClientRects().length > 0);
}

export default function useFocusTrap(active, containerRef, { initialFocusRef, onEscape } = {}) {
  const onEscapeRef = useRef(onEscape);
  onEscapeRef.current = onEscape;

  useEffect(() => {
    if (!active) return undefined;
    const previous = document.activeElement;
    const container = containerRef.current;
    const initial = initialFocusRef?.current || (container ? focusableIn(container)[0] : null);
    initial?.focus();

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onEscapeRef.current?.();
        return;
      }
      if (event.key !== "Tab" || !containerRef.current) return;
      const focusable = focusableIn(containerRef.current);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const current = document.activeElement;
      // Focus on a non-tabbable target (a heading with tabIndex -1, or outside) re-enters at the edges.
      const outside = !focusable.includes(current);
      if (event.shiftKey && (current === first || outside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (current === last || (outside && !containerRef.current.contains(current)))) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (previous && typeof previous.focus === "function" && document.contains(previous)) previous.focus();
    };
  }, [active, containerRef, initialFocusRef]);
}
