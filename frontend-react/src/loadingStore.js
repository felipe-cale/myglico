// Counts user-facing requests in flight; background polling opts out.
let pending = 0;
const listeners = new Set();

function emit() {
  listeners.forEach((listener) => listener());
}

export function beginRequest() {
  pending += 1;
  emit();
}

export function endRequest() {
  pending = Math.max(0, pending - 1);
  emit();
}

export function subscribeLoading(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function pendingRequests() {
  return pending;
}
