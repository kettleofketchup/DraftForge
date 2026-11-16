import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import axios, { type AxiosAdapter } from 'axios';
import { setI18n } from 'react-i18next';
import { afterAll, afterEach, vi } from 'vitest';

import { createI18nInstance, FALLBACK_LOCALE } from '~/i18n/config';
import type { UserType } from '~/index';

// Components rendered without an I18nextProvider fall back to this instance.
setI18n(createI18nInstance(FALLBACK_LOCALE));

// userStore fetches /current_user when it hydrates on import; answer as an anonymous visitor.
vi.mock('~/components/api/userAPI', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/userAPI')>()),
  fetchCurrentUser: vi.fn(async () => ({}) as UserType),
}));

// Unit tests must not reach the network. Any request that gets past a test's mocks is
// rejected here, logged, and fails the test in afterEach (app code often swallows the rejection).
const unmockedRequests: string[] = [];

function blockRequest(client: string, method: string, url: string): Error {
  const message = `Unmocked ${client} request in a unit test: ${method.toUpperCase()} ${url}`;
  unmockedRequests.push(message);
  console.error(message);
  return new Error(message);
}

// axios.create() copies axios.defaults, so this covers every instance the app creates.
const blockedAxiosAdapter: AxiosAdapter = async (config) => {
  throw blockRequest('axios', config.method ?? 'get', axios.getUri(config));
};
axios.defaults.adapter = blockedAxiosAdapter;

globalThis.fetch = async (input, init) => {
  const request = input instanceof Request ? input : null;
  const url = request?.url ?? String(input);
  throw blockRequest('fetch', init?.method ?? request?.method ?? 'GET', url);
};

function failOnUnmockedRequests(): void {
  if (unmockedRequests.length === 0) return;
  const found = unmockedRequests.splice(0);
  throw new Error(
    `${found.length} unmocked network request(s):\n${found.join('\n')}`,
  );
}

afterEach(() => {
  cleanup();
  failOnUnmockedRequests();
});

afterAll(failOnUnmockedRequests);
