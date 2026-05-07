export function shouldActivateDeferredSection({ isVisible, hasActivated }) {
  return Boolean(isVisible && !hasActivated);
}
