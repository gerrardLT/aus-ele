import { describe, it, expect } from 'vitest';
import { apiUrl, getApiBase } from '../lib/apiBase.js';

describe('apiUrl', () => {
  it('幂等：带 /api 前缀与不带前缀拼出同一 URL', () => {
    expect(apiUrl('/api/x')).toBe(apiUrl('/x'));
  });

  it('结果永远不出现 /api/api 双前缀', () => {
    for (const p of ['/api/v1/anomalies/NSW1', '/v1/anomalies/NSW1', '/api/investment-analysis', '/investment-analysis']) {
      expect(apiUrl(p)).not.toContain('/api/api');
    }
  });

  it('以 getApiBase() 为基址拼接', () => {
    expect(apiUrl('/years')).toBe(`${getApiBase()}/years`);
    expect(apiUrl('/api/years')).toBe(`${getApiBase()}/years`);
  });

  it('不误伤路径中段或参数中的 api 字样', () => {
    expect(apiUrl('/v1/api-data')).toBe(`${getApiBase()}/v1/api-data`);
    expect(apiUrl('/x?next=/api/y')).toBe(`${getApiBase()}/x?next=/api/y`);
  });
});
