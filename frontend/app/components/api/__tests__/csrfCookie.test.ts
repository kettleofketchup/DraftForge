import { describe, expect, it } from 'vitest';
import { readCookie } from '../utils';

describe('readCookie', () => {
  const jar = 'sessionid-s3=abc; csrftoken-s3=slot3; csrftoken=slot0; csrftoken-s4=slot4';

  it('reads the exact cookie name, not a slot-suffixed neighbour', () => {
    expect(readCookie(jar, 'csrftoken')).toBe('slot0');
    expect(readCookie(jar, 'csrftoken-s4')).toBe('slot4');
    expect(readCookie(jar, 'csrftoken-s3')).toBe('slot3');
  });

  it('does not match a name that only ends with the one asked for', () => {
    expect(readCookie('xcsrftoken=nope', 'csrftoken')).toBe('');
  });

  it('returns an empty string when the cookie is missing', () => {
    expect(readCookie('', 'csrftoken')).toBe('');
    expect(readCookie('sessionid=abc', 'csrftoken-s4')).toBe('');
  });
});
