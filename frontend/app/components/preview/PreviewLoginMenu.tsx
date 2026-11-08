/**
 * Preview Login Menu
 *
 * Test-only navbar buttons that log in as the seeded admin, staff or
 * regular test user through the backend's TEST_ENDPOINTS
 * (`/api/tests/login-<role>/`). Rendered only when
 * shouldShowTestFeatures() is true: dev mode, or a build made with
 * VITE_PREVIEW_TEST_FEATURES=true (PR preview images). Production images
 * build with the flag false, so the menu renders nothing there.
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

function loginAs(role: TestLoginRole): void {
  loginAsTestRole(role).catch((error: unknown) => {
    log.error(`Preview login failed: ${String(error)}`);
  });
}

export function PreviewLoginMenu(): JSX.Element | null {
  const show = useShowTestFeatures();
  if (!show) return null;

  return (
    <div className="flex items-center gap-1 mr-1 md:mr-2">
      {ROLES.map((role) => (
        <Button
          key={role}
          type="button"
          size="sm"
          variant="outline"
          data-testid={`preview-login-${role}`}
          onClick={() => loginAs(role)}
        >
          Login as {role}
        </Button>
      ))}
    </div>
  );
}
