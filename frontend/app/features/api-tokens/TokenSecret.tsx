import { Copy } from 'lucide-react';
import { toast } from 'sonner';

import { SecondaryButton } from '~/components/ui/buttons';
import { getLogger } from '~/lib/logger';

const log = getLogger('TokenSecret');

export interface TokenSecretProps {
  token: string;
  /** `${testIdPrefix}-secret`, `-copy` and `-once-note`. */
  testIdPrefix?: string;
}

/** A just-issued key, shown once. Never store `token` anywhere else. */
export function TokenSecret({
  token,
  testIdPrefix = 'api-token',
}: TokenSecretProps) {
  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(token);
      toast.success('Token copied');
    } catch (err) {
      log.warn('Clipboard write failed', { err });
      toast.error('Could not copy. Select the token and copy it manually.');
    }
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-stretch gap-2">
        <code
          className="min-w-0 flex-1 break-all rounded-md border border-border bg-base-900/40 p-3 font-mono text-sm select-all"
          data-testid={`${testIdPrefix}-secret`}
        >
          {token}
        </code>
        <SecondaryButton
          type="button"
          size="sm"
          className="h-auto min-h-11 self-stretch sm:min-h-8"
          onClick={copy}
          aria-label="Copy token"
          data-testid={`${testIdPrefix}-copy`}
        >
          <Copy className="size-4" />
        </SecondaryButton>
      </div>
      <p
        className="text-sm text-warning"
        data-testid={`${testIdPrefix}-once-note`}
      >
        This is the only time the full token is shown. Store it somewhere safe;
        if you lose it, revoke it and create a new one.
      </p>
    </div>
  );
}
