export function getApiBase() {
  if (import.meta.env.VITE_API_BASE) {
    return import.meta.env.VITE_API_BASE;
  }

  if (import.meta.env.DEV) {
    return '/api';
  }

  return 'http://127.0.0.1:8085/api';
}
