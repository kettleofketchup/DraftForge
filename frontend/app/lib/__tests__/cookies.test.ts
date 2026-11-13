import { describe, expect, it } from 'vitest';
import { readCookie } from '~/lib/cookies';

describe('readCookie', () => {
  const jar = 'sessionid-s3=abc; csrftoken-s3=slot3; csrftoken=slot0; csrftoken-s4=slot4';

  it('reads the exact cookie name, not a slot-suffixed neighbour', () => {
    expect(readCookie(jar, 'csrftoken')).toBe('slot0');
    expect(readCookie(jar, 'csrftoken-s4')).toBe('slot4');
    expect(readCookie(jar, 'csrftoken-s3')).toBe('slot3');
  });

  it('does not match a name that only ends with the one asked for', () => {
    expect(readCookie('xcsrftoken=nope', 'csrftoken')).toBeUndefined();
  });

  it('returns undefined when the cookie is missing', () => {
    expect(readCookie('', 'csrftoken')).toBeUndefined();
    expect(readCookie('sessionid=abc', 'csrftoken-s4')).toBeUndefined();
  });

  it('URL-decodes values', () => {
    expect(readCookie('df-locale=pt%2DBR; other=1', 'df-locale')).toBe('pt-BR');
    expect(readCookie('a=x%20y', 'a')).toBe('x y');
  });

  it('keeps values with an equals sign intact', () => {
    expect(readCookie('tok=ab==', 'tok')).toBe('ab==');
  });

  it('returns the raw value when it is not valid URI encoding', () => {
    expect(readCookie('a=100%', 'a')).toBe('100%');
  });
});
