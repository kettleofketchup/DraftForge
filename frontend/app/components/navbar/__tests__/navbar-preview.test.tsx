// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { ResponsiveAppBar } from '../navbar';

const shouldShowTestFeatures = vi.hoisted(() => vi.fn<() => boolean>());
vi.mock('~/lib/test-utils', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/lib/test-utils')>()),
  shouldShowTestFeatures,
}));

// The real store fetches /current_user on rehydrate; the navbar only reads currentUser.
vi.mock('~/store/userStore', () => ({
  useUserStore: (selector: (state: { currentUser: object }) => unknown) =>
    selector({ currentUser: {} }),
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

// Siblings with their own data hooks are out of scope for this wiring test.
vi.mock('../login', () => ({ LoginWithDiscordButton: () => null }));
vi.mock('../MobileNav', () => ({ MobileNav: () => null }));
vi.mock('../PageNavBar', () => ({ PageNavBar: () => null }));

function renderNavbar() {
  return render(
    <TooltipProvider>
      <MemoryRouter>
        <ResponsiveAppBar />
      </MemoryRouter>
    </TooltipProvider>,
  );
}

describe('navbar preview login wiring', () => {
  beforeEach(() => {
    // ExternalLinks fetches the GitHub star count on mount.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the preview login menu when test features are on', () => {
    shouldShowTestFeatures.mockReturnValue(true);
    renderNavbar();
    expect(screen.getByTestId('preview-login-admin')).toBeInTheDocument();
  });

  it('omits the preview login menu when test features are off', () => {
    shouldShowTestFeatures.mockReturnValue(false);
    renderNavbar();
    expect(screen.queryByTestId('preview-login-admin')).not.toBeInTheDocument();
  });
});
