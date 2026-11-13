import { createCookie } from 'react-router';
import { describe, expect, it } from 'vitest';

import { localeCookie, resolveRequestLocale } from '../i18n.server';
import { decodeLocaleCookieValue, readLocaleCookie, serializeLocaleCookie } from '../localeCookie';

async function legacyHeader(locale: string): Promise<string> {
  const setCookie = await createCookie('df-locale').serialize(locale);
  return setCookie.split(';')[0];
}

describe('decodeLocaleCookieValue', () => {
  it('accepts the plain format', () => {
    expect(decodeLocaleCookieValue('es')).toBe('es');
    expect(decodeLocaleCookieValue('en')).toBe('en');
  });

  it('accepts the legacy base64 JSON format', () => {
    expect(decodeLocaleCookieValue('ImVzIg==')).toBe('es');
    expect(decodeLocaleCookieValue('ImVuIg==')).toBe('en');
  });

  it('rejects unsupported, malformed and empty values', () => {
    expect(decodeLocaleCookieValue('fr')).toBeUndefined();
    expect(decodeLocaleCookieValue(btoa('"fr"'))).toBeUndefined();
    expect(decodeLocaleCookieValue(btoa('{"a":1}'))).toBeUndefined();
    expect(decodeLocaleCookieValue('!!notbase64')).toBeUndefined();
    expect(decodeLocaleCookieValue('')).toBeUndefined();
    expect(decodeLocaleCookieValue(undefined)).toBeUndefined();
  });
});

describe('readLocaleCookie', () => {
  it('does not ask to rewrite a plain cookie', () => {
    expect(readLocaleCookie('a=1; df-locale=es')).toEqual({ locale: 'es', needsRewrite: false });
  });

  it('decodes a cookie written by React Router createCookie and asks to rewrite it', async () => {
    const header = await legacyHeader('es');
    expect(header).toBe('df-locale=ImVzIg%3D%3D');
    expect(readLocaleCookie(header)).toEqual({ locale: 'es', needsRewrite: true });
  });

  it('reports nothing for a missing or unusable cookie', () => {
    expect(readLocaleCookie(null)).toEqual({ locale: undefined, needsRewrite: false });
    expect(readLocaleCookie('df-locale=fr')).toEqual({ locale: undefined, needsRewrite: false });
  });
});

describe('serializeLocaleCookie', () => {
  it('writes the plain value with a one-year lifetime', () => {
    expect(serializeLocaleCookie('es', false)).toBe(
      'df-locale=es; Path=/; Max-Age=31536000; SameSite=Lax',
    );
    expect(serializeLocaleCookie('es', true)).toMatch(/; Secure$/);
  });
});

describe('server localeCookie', () => {
  it('serializes the plain format the client reads', async () => {
    const setCookie = await localeCookie.serialize('es');
    expect(setCookie.startsWith('df-locale=es;')).toBe(true);
    expect(readLocaleCookie(setCookie.split(';')[0]).locale).toBe('es');
  });

  it('parses both formats', async () => {
    expect(await localeCookie.parse('df-locale=es')).toBe('es');
    expect(await localeCookie.parse(await legacyHeader('es'))).toBe('es');
    expect(await localeCookie.parse('df-locale=fr')).toBeNull();
    expect(await localeCookie.parse(null)).toBeNull();
  });
});

describe('resolveRequestLocale', () => {
  function request(cookie: string | null, search = ''): Request {
    const headers = new Headers({ 'Accept-Language': 'en-US' });
    if (cookie) headers.set('Cookie', cookie);
    return new Request(`https://example.test/tournaments${search}`, { headers });
  }

  it('honours a plain cookie without rewriting it', async () => {
    expect(await resolveRequestLocale(request('df-locale=es'))).toEqual({ locale: 'es', setCookie: null });
  });

  it('honours a legacy cookie and rewrites it as plain', async () => {
    const { locale, setCookie } = await resolveRequestLocale(request(await legacyHeader('es')));
    expect(locale).toBe('es');
    expect(setCookie).toMatch(/^df-locale=es;/);
  });

  it('writes ?lang= as a plain cookie over an existing one', async () => {
    const { locale, setCookie } = await resolveRequestLocale(request('df-locale=es', '?lang=en'));
    expect(locale).toBe('en');
    expect(setCookie).toMatch(/^df-locale=en;/);
  });

  it('sets the Accept-Language locale when no cookie exists', async () => {
    const { locale, setCookie } = await resolveRequestLocale(request(null));
    expect(locale).toBe('en');
    expect(setCookie).toMatch(/^df-locale=en;/);
  });
});
