export function resolveRootPage(pathname = '/') {
  if (pathname.startsWith('/fingrid')) {
    return 'fingrid';
  }
  if (pathname.startsWith('/developer')) {
    return 'developer';
  }
  return 'aemo';
}
