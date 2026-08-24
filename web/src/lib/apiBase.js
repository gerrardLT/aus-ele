export function getApiBase() {
  if (import.meta.env.VITE_API_BASE) {
    return import.meta.env.VITE_API_BASE;
  }

  if (import.meta.env.DEV) {
    return '/api';
  }

  return 'http://127.0.0.1:8085/api';
}

/**
 * 拼接完整 API URL（幂等）。
 * 传入路径若已带 '/api' 前缀会自动去除，避免 '/api/api/...' 双前缀。
 * @param {string} path 以 '/' 开头的接口路径，如 '/v1/anomalies/NSW1' 或 '/api/v1/...'
 */
export function apiUrl(path) {
  const clean = String(path).replace(/^\/api(?=\/)/, '');
  return `${getApiBase()}${clean}`;
}
