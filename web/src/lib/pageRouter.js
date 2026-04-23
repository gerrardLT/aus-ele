export function resolveRootPage(pathname = '/') {
  return pathname.startsWith('/fingrid') ? 'fingrid' : 'aemo';
}
