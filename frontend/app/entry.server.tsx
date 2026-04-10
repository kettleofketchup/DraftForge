// Known acceptable hydration mismatches (cosmetic, React handles gracefully):
// - Navbar: Admin link only appears after client hydration for staff users
//   (server renders without auth state, client adds it from sessionStorage)
// - Zustand persist: hasHydrated is false during SSR, true after client hydration

import { PassThrough } from 'node:stream';

import { createReadableStreamFromReadable } from '@react-router/node';
import type { EntryContext } from 'react-router';
import { ServerRouter } from 'react-router';
import { renderToPipeableStream } from 'react-dom/server';

export default function handleRequest(
  request: Request,
  responseStatusCode: number,
  responseHeaders: Headers,
  routerContext: EntryContext,
) {
  return new Promise((resolve, reject) => {
    const { pipe, abort } = renderToPipeableStream(
      <ServerRouter context={routerContext} url={request.url} />,
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
