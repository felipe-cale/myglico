// Counts user-facing requests in flight and keeps their controllers so the
// overlay can cancel them; background polling opts out of both.
let pending = 0;
const controllers = new Set();
const listeners = new Set();

function emit() {
  listeners.forEach((listener) => listener());
}

export function beginRequest(controller) {
  pending += 1;
  if (controller) controllers.add(controller);
  emit();
}

export function endRequest(controller) {
  pending = Math.max(0, pending - 1);
  if (controller) controllers.delete(controller);
  emit();
}

export function cancelPendingRequests() {
  Array.from(controllers).forEach((controller) => controller.abort());
}

export function subscribeLoading(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function pendingRequests() {
  return pending;
}
