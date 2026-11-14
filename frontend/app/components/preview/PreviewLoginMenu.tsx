/**
 * Preview Login Menu
 *
 * Test-only buttons that log in as the seeded admin, staff or regular test
 * user through the backend's TEST_ENDPOINTS (`/api/tests/login-<role>/`).
 * Rendered only when shouldShowTestFeatures() is true: dev mode, or a build
 * made with VITE_PREVIEW_TEST_FEATURES=true (PR preview images). Production
 * images build with the flag false, so the menu renders nothing there.
 *
 * The navbar placement shows from md up, where the mobile nav toggle is gone;
 * below md the drawer placement inside MobileNav takes over.
 *
 * useShowTestFeatures() renders nothing on the server and decides after
 * hydration, so the hydrated tree never differs from the server's.
 */
import type { JSX } from 'react';
import { Button } from '~/components/ui/button';
import { useShowTestFeatures } from '~/hooks/useShowTestFeatures';
import { getLogger } from '~/lib/logger';
import { loginAsTestRole, type TestLoginRole } from '~/lib/test-utils';

const log = getLogger('PreviewLoginMenu');

const ROLES: readonly TestLoginRole[] = ['admin', 'staff', 'user'];

export type PreviewLoginPlacement = 'navbar' | 'drawer';

interface PreviewLoginMenuProps {
  placement?: PreviewLoginPlacement;
}

function loginAs(role: TestLoginRole): void {
  loginAsTestRole(role).catch((error: unknown) => {
    log.error(`Preview login failed: ${String(error)}`);
  });
}

export function PreviewLoginMenu({
  placement = 'navbar',
}: PreviewLoginMenuProps): JSX.Element | null {
  const show = useShowTestFeatures();
  if (!show) return null;

  const inDrawer = placement === 'drawer';

  return (
    <div
      className={
        inDrawer
          ? 'flex flex-col gap-2 px-3 mt-4'
          : 'hidden md:flex items-center gap-1 mr-2'
      }
      data-testid={
        inDrawer ? 'mobile-preview-login-menu' : 'preview-login-menu'
      }
    >
      {ROLES.map((role) => (
        <Button
          key={role}
          type="button"
          size="sm"
          variant="outline"
          aria-label={`Login as ${role}`}
          data-testid={
            inDrawer ? `mobile-preview-login-${role}` : `preview-login-${role}`
          }
          onClick={() => loginAs(role)}
        >
          <span className={inDrawer ? undefined : 'hidden lg:inline'}>
            Login as
          </span>
          {role}
        </Button>
      ))}
    </div>
  );
}
