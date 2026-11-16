import { PRERENDER_PATHS } from './prerender';

export type SessionHint = 'anonymous' | 'unknown';

// Same test as $df_session in nginx/default.template.conf, which keys the SSR
// cache on it: "sessionid" in prod, "sessionid-sN" on test stack slot N.
const SESSION_COOKIE = /(?:^|;\s*)sessionid(?:-[A-Za-z0-9]+)?=/;

// 'anonymous' only when the request provably has no session. A stale session
// cookie still reads 'unknown', so SSR never bakes the login button for a
// visitor who may be logged in.
export function resolveSessionHint(
  cookieHeader: string | null,
  pathname: string,
): SessionHint {
  if ((PRERENDER_PATHS as readonly string[]).includes(pathname))
    return 'unknown';
  return SESSION_COOKIE.test(cookieHeader ?? '') ? 'unknown' : 'anonymous';
}
