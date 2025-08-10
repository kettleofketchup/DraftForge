import { scan } from 'react-scan';

import { useEffect } from 'react';
import {
  isRouteErrorResponse,
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
} from 'react-router';
import { Toaster } from '~/components/ui/sonner';
import type { Route } from './+types/root';
import './app.css';
import ResponsiveAppBar from './components/navbar/navbar';
import { useUserStore } from './store/userStore';

export const links: Route.LinksFunction = () => [
  { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
  {
    rel: 'preconnect',
    href: 'https://fonts.gstatic.com',
    crossOrigin: 'anonymous',
  },
  {
    rel: 'stylesheet',
    href: 'https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap',
  },
];

export function Layout({ children }: { children: React.ReactNode }) {
  if (import.meta.env.DEV) {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
  }

  useEffect(() => {
    // Make sure to run react-scan only after hydration
    // if (import.meta.env.DEV) {
    scan({
      enabled: process.env.NODE_ENV === 'development',
      trackUnnecessaryRenders: true,
      showToolbar: true,
      showNotificationCount: true,
    });
    // }
  }, []);

  const currentUser = useUserStore((state) => state.currentUser); // Zustand setter
  const getCurrentUser = useUserStore((state) => state.getCurrentUser); // Zustand setter

  const hasHydrated = useUserStore((state) => state.hasHydrated); // Zustand setter

  useEffect(() => {
    if (hasHydrated && currentUser.username === undefined) {
      getCurrentUser();
    }
  }, [hasHydrated]);
  return (
    <html lang="en" className="dark" data-theme="dark">
      <head>
        {/* {import.meta.env.DEV && (
          <script src="https://unpkg.com/react-scan/dist/auto.global.js" />
        )} */}
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <Meta />
        <Links />
      </head>
      <body>
        {/* Your component tree. Now you can override Material UI's styles. */}

        <div className="flex flex-col h-screen flex w-screen h-screen justify-between">
          <ResponsiveAppBar />
          <div id="outlet_root" className="flex-grow overflow-x-hidden">
            {children}
          </div>
        </div>
        <Toaster richColors closeButton position="top-center" />

        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

export default function App() {
  return (
    <>
      <Outlet />
    </>
  );
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  let message = 'Oops!';
  let details = 'An unexpected error occurred.';
  let stack: string | undefined;

  if (isRouteErrorResponse(error)) {
    message = error.status === 404 ? '404' : 'Error';
    details =
      error.status === 404
        ? 'The requested page could not be found.'
        : error.statusText || details;
  } else if (import.meta.env.DEV && error && error instanceof Error) {
    details = error.message;
    stack = error.stack;
  }

  return (
    <main className="pt-16 p-4 container mx-auto">
      <h1>{message}</h1>
      <p>{details}</p>
      {stack && (
        <pre className="w-full p-4 overflow-x-auto">
          <code>{stack}</code>
        </pre>
      )}
    </main>
  );
}
