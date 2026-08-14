export function resolveRootPage(pathname = '/') {
  if (pathname.startsWith('/login')) {
    return 'login';
  }
  if (pathname.startsWith('/invite')) {
    return 'invite';
  }
  if (pathname.startsWith('/account')) {
    return 'account';
  }
  if (pathname.startsWith('/pricing')) {
    return 'pricing';
  }
  if (pathname.startsWith('/legal')) {
    return 'legal';
  }
  if (pathname.startsWith('/reports')) {
    return 'reports';
  }
  if (pathname.startsWith('/help')) {
    return 'help';
  }
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
