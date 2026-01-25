import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect } from 'react';
import {
  isRouteErrorResponse,
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
} from 'react-router';
import { ScrollArea } from '~/components/ui/scroll-area';
import { Toaster } from '~/components/ui/sonner';
import { SharedPopoverProvider } from '~/components/ui/shared-popover-context';
import { SharedPopoverRenderer } from '~/components/ui/shared-popover-renderer';
import { TooltipProvider } from '~/components/ui/tooltip';
import { getLogger } from '~/lib/logger';
import type { Route } from './+types/root';
import './app.css';
import { ActiveDraftBanner } from './components/draft/ActiveDraftBanner';
import { FloatingDraftIndicator } from './components/draft/FloatingDraftIndicator';
import ResponsiveAppBar from './components/navbar/navbar';

('use client');

const log = getLogger('root');

// ✅ All fonts and external styles live here
export const links: Route.LinksFunction = () => [];

// ✅ Meta tags live here
export const meta: Route.MetaFunction = () => [
  { title: 'Tournament Tracker' },
  { name: 'description', content: 'Track your tournament progress' },
  { name: 'viewport', content: 'width=device-width, initial-scale=1' },
  { charSet: 'utf-8' },
];

// ✅ Dev-only scripts injected client-side only, never during SSR
export function DevScripts() {
  useEffect(() => {
    log.debug(
      'DevScripts loaded',
      import.meta.env,
      'process.env',
      process.env.NODE_ENV,
    );

    if (process.env.NODE_ENV === 'dev' || process.env.NODE_ENV === 'test') {
      import('react-scan').then((module) => {
        module.scan({
          enabled: import.meta.env.DEV === true,
          trackUnnecessaryRenders: import.meta.env.DEV === true,
          showToolbar: import.meta.env.DEV === true,
        });
      });
    }
  }, []);

  return null;
}

// Create a client outside component to avoid recreation on renders
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
});

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" data-theme="dark">
      <head suppressHydrationWarning={true}>
        <Meta />
        <Links />
      </head>
      <body>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider delayDuration={300}>
          <SharedPopoverProvider>
            <div className="flex flex-col w-screen h-screen justify-between">
              <ResponsiveAppBar />
              <ActiveDraftBanner />
              <ScrollArea id="outlet_root" className="flex-grow h-0">
                {children}
              </ScrollArea>
            </div>
            <Toaster richColors closeButton position="top-center" />
            <FloatingDraftIndicator />
            <SharedPopoverRenderer />
          </SharedPopoverProvider>
          </TooltipProvider>
        </QueryClientProvider>

        <ScrollRestoration />
        <Scripts />
        <DevScripts />
      </body>
    </html>
  );
}

export default function App() {
  return <Outlet />;
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
