import { SecondaryButton } from '~/components/ui/buttons';
import { brandErrorBg } from '~/components/ui/buttons/styles';
import { cn } from '~/lib/utils';

export function ListError({
  testId,
  message,
  onRetry,
}: {
  testId: string;
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      data-testid={testId}
      role="alert"
      className={cn(brandErrorBg, 'rounded-lg p-4')}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-error">{message}</p>
        <SecondaryButton size="sm" onClick={onRetry}>
          Retry
        </SecondaryButton>
      </div>
    </div>
  );
}
