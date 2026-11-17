import { describe, expect, it } from 'vitest';
import { PRERENDER_PATHS } from '~/lib/prerender';
import { resolveSessionHint } from '~/lib/sessionHint';

describe('resolveSessionHint', () => {
  it('is anonymous when the request carries no cookies', () => {
    expect(resolveSessionHint(null, '/tournaments')).toBe('anonymous');
    expect(resolveSessionHint('', '/tournaments')).toBe('anonymous');
  });

  it('is anonymous when cookies exist but none is a session cookie', () => {
    expect(
      resolveSessionHint('df-locale=es; csrftoken=abc', '/tournaments'),
    ).toBe('anonymous');
    expect(
      resolveSessionHint('notsessionid=x; sessionidx=y', '/tournaments'),
    ).toBe('anonymous');
  });

  it('is unknown when a session cookie is present', () => {
    expect(
      resolveSessionHint('df-locale=es; sessionid=abc', '/tournaments'),
    ).toBe('unknown');
  });

  it('treats slot-suffixed session cookies as sessions', () => {
    expect(
      resolveSessionHint('csrftoken=a; sessionid-s3=x', '/tournaments'),
    ).toBe('unknown');
  });

  it('is unknown on prerendered paths, whose HTML every visitor shares', () => {
    for (const path of PRERENDER_PATHS) {
      expect(resolveSessionHint(null, path)).toBe('unknown');
    }
  });
});
