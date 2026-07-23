export function resolveRootPage(pathname = '/') {
  if (pathname.startsWith('/wem')) {
    return 'wem';
  }
  if (pathname.startsWith('/finland')) {
    return 'finland';
  }
  if (pathname.startsWith('/fingrid')) {
    return 'fingrid';
  }
  if (pathname.startsWith('/developer')) {
    return 'developer';
  }
  if (pathname.startsWith('/agent')) {
    return 'agent';
  }
  return 'aemo';
}
