import useMediaQuery from "./useMediaQuery";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

export function preferredScrollBehavior() {
  const reduced = typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(REDUCED_MOTION_QUERY).matches;
  return reduced ? "auto" : "smooth";
}

export default function usePrefersReducedMotion() {
  return useMediaQuery(REDUCED_MOTION_QUERY);
}
