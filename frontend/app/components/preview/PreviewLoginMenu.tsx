/**
 * Preview Login Menu
 *
 * Test-only navbar buttons that log in as the seeded admin, staff or
 * regular test user through the backend's TEST_ENDPOINTS
 * (`/api/tests/login-<role>/`). Rendered only when
 * shouldShowTestFeatures() is true: dev mode, or a build made with
 * VITE_PREVIEW_TEST_FEATURES=true (PR preview images). Production images
 * build with the flag false, so the menu renders nothing there.
 */
import type { JSX } from 'react';
import { Button } from '~/components/ui/button';
import { getLogger } from '~/lib/logger';
import { shouldShowTestFeatures } from '~/lib/test-utils';

const log = getLogger('PreviewLoginMenu');

type PreviewRole = 'admin' | 'staff' | 'user';

const ROLES: readonly PreviewRole[] = ['admin', 'staff', 'user'];

async function loginAs(role: PreviewRole): Promise<void> {
  const response = await fetch(`/api/tests/login-${role}/`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!response.ok) {
    log.error(`Preview login as ${role} failed: ${response.status}`);
    return;
  }
  window.location.reload();
}

export function PreviewLoginMenu(): JSX.Element | null {
  if (!shouldShowTestFeatures()) return null;

  return (
    <div className="flex items-center gap-1 mr-1 md:mr-2">
      {ROLES.map((role) => (
        <Button
          key={role}
          type="button"
          size="sm"
          variant="outline"
          data-testid={`preview-login-${role}`}
          onClick={() => void loginAs(role)}
        >
          Login as {role}
        </Button>
      ))}
    </div>
  );
}
