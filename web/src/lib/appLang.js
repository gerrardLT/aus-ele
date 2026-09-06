// web/src/lib/appLang.js
// 界面语言的单一读取点（2026-09-06，服务 R3.3/R3.5 的全局 chrome）。
//
// 为什么需要它：侧边栏/抽屉/命令面板挂在路由之外（main.jsx 的 Root），拿不到页面自己的
// `useState(lang)`。此前每个页面各自写了一份 `readPreferredLang()`（FinlandPage、
// FingridPage、DeveloperPortalPage 三处字面重复），我若再抄第四份，就是把一个已知的
// 「四份实现可以给出四个答案」的局面继续放大。
//
// 本批次**不动那三个页面**：R6.11 对 i18n 的规定是「不重写既有结构、只加新层」，
// 而 fingridPage.test.js:96 断言该文件里存在 `const [lang, setLang]` 与
// `readPreferredLang` 的调用形态。收敛那三处登记为 R6.11 的接线项。

export const LANG_STORAGE_KEY = 'app_lang';

/** 读取当前界面语言。localStorage 不可用（隐私模式/SSR）时回落 'zh'，与既有页面一致。 */
export function readAppLang() {
  try {
    const stored = globalThis.localStorage?.getItem(LANG_STORAGE_KEY);
    return stored === 'en' ? 'en' : 'zh';
  } catch {
    return 'zh';
  }
}
