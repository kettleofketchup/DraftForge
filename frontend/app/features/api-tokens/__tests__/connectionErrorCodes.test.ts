import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { CONNECTION_ERROR_MESSAGES } from '../connectionSchemas';

const backendOrg = fileURLToPath(
  new URL('../../../../../backend/org/', import.meta.url),
);

function read(path: string): string {
  return readFileSync(`${backendOrg}${path}`, 'utf8');
}

function codes(source: string, patterns: readonly RegExp[]): Set<string> {
  const found = new Set<string>();
  for (const pattern of patterns) {
    for (const match of source.matchAll(pattern)) {
      for (const code of match.slice(1)) found.add(code);
    }
  }
  return found;
}

const CONNECTION_PATTERNS = [
  /Error\("([a-z_]+)"/g,
  /_invalid\("([a-z_]+)"/g,
  /"code": "([a-z_]+)"/g,
  /error_code="([a-z_]+)"/g,
  /last_reason="([a-z_]+)"/g,
  /_settle\(\w+, [\w.]+, "([a-z_]+)"\)/g,
  /_Hold\([\w.]+, "([a-z_]+)"\)/g,
];

const PROMOTION_PATTERNS = [
  /OutcomeKind\.\w+,\s*"([a-z_]+)"/g,
  /_held\("([a-z_]+)"\)/g,
  /^\s+\d{3}: "([a-z_]+)",$/gm,
  /\.get\(status, "([a-z_]+)"\)/g,
  /^[A-Z_]+: Final\[str\] = "([a-z_]+)"$/gm,
  /frozenset\(\{"([a-z_]+)", "([a-z_]+)"\}\)/g,
];

describe('CONNECTION_ERROR_MESSAGES', () => {
  it('has plain-language text for every backend code that reaches the UI', () => {
    const found = new Set<string>();
    const dir = `${backendOrg}api_connections/`;
    for (const file of readdirSync(dir).filter((f) => f.endsWith('.py'))) {
      for (const code of codes(
        read(`api_connections/${file}`),
        CONNECTION_PATTERNS,
      )) {
        found.add(code);
      }
    }
    for (const file of [
      'integration/adaptor_client.py',
      'integration/dispatch.py',
      'integration/lifecycle.py',
    ]) {
      for (const code of codes(read(file), PROMOTION_PATTERNS)) found.add(code);
    }
    const ignored = new Set(['applied', 'already_contacted', 'canceled']);
    const missing = [...found]
      .filter((code) => !ignored.has(code))
      .filter((code) => !(code in CONNECTION_ERROR_MESSAGES))
      .sort();
    expect(found.size).toBeGreaterThan(40);
    expect(missing).toEqual([]);
  });
});
