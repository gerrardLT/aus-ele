/**
 * useDebounce — U2: 延迟值 hook
 *
 * 返回 debounce 后的值，用于 slider 拖动时避免频繁 API 调用。
 */

import { useState, useEffect } from 'react';

export function useDebounce(value, delay = 500) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}
