import { describe, expect, it } from 'vitest';
import { safeHref, safeImageSrc } from '../safeHref';

describe('safeHref', () => {
  it('passes http and https URLs', () => {
    expect(safeHref('http://example.com/a?b=1')).toBe(
      'http://example.com/a?b=1',
    );
    expect(safeHref('https://example.com')).toBe('https://example.com');
  });

  it.each([
    ['javascript:alert(1)'],
    ['JavaScript:alert(1)'],
    ['data:text/html,<b>x</b>'],
    ['/relative'],
    ['not a url'],
    [''],
    [undefined],
  ])('rejects %s', (url) => {
    expect(safeHref(url)).toBeUndefined();
  });
});

describe('safeImageSrc', () => {
  it('passes https only', () => {
    expect(safeImageSrc('https://cdn.example.com/x.png')).toBe(
      'https://cdn.example.com/x.png',
    );
    expect(safeImageSrc('http://x')).toBeUndefined();
    expect(safeImageSrc('data:image/png;base64,AAAA')).toBeUndefined();
    expect(safeImageSrc(undefined)).toBeUndefined();
  });
});
