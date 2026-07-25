/**
 * ThemeContext — U1: 暗色/亮色主题切换
 *
 * 提供 useTheme() hook，管理 data-theme 属性并持久化到 localStorage。
 * 默认暗色（dark-first），对齐 Linear/Datadog 2026 标杆。
 */

import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const ThemeContext = createContext({ theme: 'dark', toggleTheme: () => {} });

function getInitialTheme() {
  try {
    const stored = localStorage.getItem('app_theme');
    if (stored === 'light' || stored === 'dark') return stored;
  } catch { /* ignore */ }
  return 'dark'; // dark-first default
}

// Apply theme immediately on module load to prevent FOUC
const _initialTheme = getInitialTheme();
if (typeof document !== 'undefined') {
  document.documentElement.setAttribute('data-theme', _initialTheme);
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('app_theme', theme); } catch { /* ignore */ }
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
