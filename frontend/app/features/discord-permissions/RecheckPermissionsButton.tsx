import { RefreshCw } from 'lucide-react';
import { SecondaryButton } from '~/components/ui/buttons/SecondaryButton';

export function RecheckPermissionsButton({
  onRecheck,
  isRechecking,
  'data-testid': testId = 'discord-permission-recheck',
}: {
  onRecheck: () => Promise<void>;
  isRechecking: boolean;
  'data-testid'?: string;
}) {
  return (
    <SecondaryButton
      type="button"
      size="sm"
      disabled={isRechecking}
      aria-busy={isRechecking}
      data-testid={testId}
      onClick={() => void onRecheck()}
    >
      <RefreshCw className="size-4" aria-hidden="true" />
      {isRechecking ? 'Checking…' : 'Recheck permissions'}
    </SecondaryButton>
  );
}
