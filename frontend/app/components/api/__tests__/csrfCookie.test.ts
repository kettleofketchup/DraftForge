// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';

import { getCsrfToken } from '../utils';

describe('getCsrfToken', () => {
  afterEach(() => {
    for (const name of ['csrftoken', 'csrftoken-s3']) {
      document.cookie = `${name}=; path=/; max-age=0`;
    }
  });

  it('reads the csrftoken cookie by exact name', () => {
    document.cookie = 'csrftoken-s3=other; path=/';
    document.cookie = 'csrftoken=mine; path=/';
    expect(getCsrfToken()).toBe('mine');
  });

  it('returns an empty string without a csrftoken cookie', () => {
    expect(getCsrfToken()).toBe('');
  });
});
