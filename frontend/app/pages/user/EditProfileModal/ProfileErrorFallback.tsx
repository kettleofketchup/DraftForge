import type { FallbackProps } from 'react-error-boundary';

import { SecondaryButton } from '~/components/ui/buttons/SecondaryButton';

export function ProfileErrorFallback({ error, resetErrorBoundary }: FallbackProps) {
  const message = error instanceof Error ? error.message : '';
  return (
    <div className="flex flex-col gap-2 p-4">
      <p className="text-sm text-base-content">
        Could not load profile. {message}
      </p>
      <SecondaryButton type="button" onClick={() => resetErrorBoundary()}>
        Retry
      </SecondaryButton>
    </div>
  );
}
