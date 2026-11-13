// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';

import { resolveLocale } from '../client';

function setUrl(search: string): void {
  window.history.replaceState(null, '', `/${search}`);
}

function rawLocaleCookie(): string | undefined {
  return document.cookie
    .split('; ')
    .find((c) => c.startsWith('df-locale='))
    ?.slice('df-locale='.length);
}

afterEach(() => {
  document.cookie = 'df-locale=; Path=/; Max-Age=0';
  document.documentElement.lang = '';
  setUrl('');
});

describe('resolveLocale', () => {
  it('reads a plain cookie and leaves it alone', () => {
    document.cookie = 'df-locale=es; Path=/';
    expect(resolveLocale()).toBe('es');
    expect(rawLocaleCookie()).toBe('es');
  });

  it('reads a legacy base64 JSON cookie and rewrites it as plain', () => {
    document.cookie = 'df-locale=ImVzIg%3D%3D; Path=/';
    expect(resolveLocale()).toBe('es');
    expect(rawLocaleCookie()).toBe('es');
  });

  it('migrates a legacy cookie even when <html lang> decides the locale', () => {
    document.cookie = 'df-locale=ImVzIg%3D%3D; Path=/';
    document.documentElement.lang = 'es';
    expect(resolveLocale()).toBe('es');
    expect(rawLocaleCookie()).toBe('es');
  });

  it('writes ?lang= as a plain cookie, replacing a legacy one', () => {
    document.cookie = 'df-locale=ImVuIg%3D%3D; Path=/';
    setUrl('?lang=es');
    expect(resolveLocale()).toBe('es');
    expect(rawLocaleCookie()).toBe('es');
  });

  it('prefers <html lang> over the cookie', () => {
    document.cookie = 'df-locale=es; Path=/';
    document.documentElement.lang = 'en';
    expect(resolveLocale()).toBe('en');
  });

  it('ignores an unusable cookie and falls back to English', () => {
    document.cookie = 'df-locale=fr; Path=/';
    expect(resolveLocale()).toBe('en');
    expect(rawLocaleCookie()).toBe('fr');
  });
});
