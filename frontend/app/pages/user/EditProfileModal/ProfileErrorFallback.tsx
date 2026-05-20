import type { FallbackProps } from 'react-error-boundary';

export function ProfileErrorFallback({ error, resetErrorBoundary }: FallbackProps) {
  const message = error instanceof Error ? error.message : '';
  return (
    <div className="p-4 space-y-2">
      <p className="text-sm text-base-content">
        Could not load profile. {message}
      </p>
      <button
        type="button"
        onClick={() => resetErrorBoundary()}
        className="underline text-sm"
      >
        Retry
      </button>
    </div>
  );
}
