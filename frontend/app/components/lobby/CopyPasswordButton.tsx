import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Copy } from 'lucide-react';
import { SecondaryButton } from '~/components/ui/buttons';

interface CopyPasswordButtonProps {
  password: string;
  'data-testid'?: string;
}

/** Copies a lobby password to the clipboard, with a toast either way. */
export function CopyPasswordButton({ password, ...props }: CopyPasswordButtonProps) {
  const { t } = useTranslation('lobby');
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(password);
      toast.success(t('password.copy.done'));
    } catch {
      toast.error(t('password.copy.failed'));
    }
  };
  return (
    <SecondaryButton
      type="button"
      size="sm"
      onClick={copy}
      aria-label={t('password.copy.label')}
      data-testid={props['data-testid']}
    >
      <Copy className="size-4" />
    </SecondaryButton>
  );
}
