// Known acceptable hydration mismatches (cosmetic, React handles gracefully):
// - Navbar: Admin link only appears after client hydration for staff users
//   (server renders without auth state, client adds it from sessionStorage)
// - Zustand persist: hasHydrated is false during SSR, true after client hydration

import { PassThrough } from 'node:stream';

import { createReadableStreamFromReadable } from '@react-router/node';
import type { EntryContext } from 'react-router';
import { ServerRouter } from 'react-router';
import { renderToPipeableStream } from 'react-dom/server';
import { I18nextProvider } from 'react-i18next';
import { createI18nInstance } from './i18n/config';
import { i18nServer } from './i18n/i18n.server';

export default async function handleRequest(
  request: Request,
  responseStatusCode: number,
  responseHeaders: Headers,
  routerContext: EntryContext,
) {
  const locale = await i18nServer.getLocale(request);
  const i18n = createI18nInstance(locale);

  return new Promise((resolve, reject) => {
    const { pipe, abort } = renderToPipeableStream(
      <I18nextProvider i18n={i18n}>
        <ServerRouter context={routerContext} url={request.url} />
      </I18nextProvider>,
      {
        onShellReady() {
          responseHeaders.set('Content-Type', 'text/html');
          const body = new PassThrough();
          const stream = createReadableStreamFromReadable(body);
          resolve(
            new Response(stream, {
              headers: responseHeaders,
              status: responseStatusCode,
            }),
          );
          pipe(body);
        },
        onShellError(error: unknown) {
          reject(error);
        },
      },
    );

    setTimeout(abort, 5000);
  });
}
