import { useQuery, type QueryKey } from '@tanstack/react-query';
import { Eye } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  SecondaryButton,
  type SecondaryButtonProps,
} from '~/components/ui/buttons';
import { InfoDialog } from '~/components/ui/dialogs';
import { Skeleton } from '~/components/ui/skeleton';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { extractApiError } from '~/lib/apiError';

export type DiscordPreviewRenderControls = {
  closeAndThen: (callback: () => void) => void;
};

type FetchedProps<T> = {
  fetchPreview: () => Promise<T>;
  render: (data: T, controls: DiscordPreviewRenderControls) => ReactNode;
};

type StaticProps = {
  fetchPreview?: undefined;
  render?: undefined;
};

export type DiscordPreviewButtonProps<T> = {
  queryKey: QueryKey;
  title: string;
  label?: string;
  ariaLabel?: string;
  description?: string;
  body?: ReactNode;
  disabled?: boolean;
  disabledReason?: string;
  'data-testid'?: string;
} & (FetchedProps<T> | StaticProps) &
  Omit<
    SecondaryButtonProps,
    'type' | 'onClick' | 'title' | 'children' | 'disabled'
  >;

function PreviewResult<T>({
  queryKey,
  fetchPreview,
  render,
  controls,
}: {
  queryKey: QueryKey;
  controls: DiscordPreviewRenderControls;
} & FetchedProps<T>) {
  const { t } = useTranslation('discordPreview');
  const query = useQuery({
    queryKey,
    queryFn: fetchPreview,
    staleTime: 0,
    gcTime: 0,
    retry: false,
  });

  if (query.isPending) {
    return (
      <div
        data-testid="discord-preview-loading"
        role="status"
        aria-label={t('dialog.loading')}
        className="space-y-2"
      >
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }

  if (query.isError) {
    return (
      <div role="alert" className="space-y-3">
        <p className="text-sm text-destructive">
          {extractApiError(query.error) ?? t('error.generic')}
        </p>
        <SecondaryButton
          size="sm"
          onClick={() => void query.refetch()}
          type="button"
        >
          {t('error.retry')}
        </SecondaryButton>
      </div>
    );
  }

  return <>{render(query.data, controls)}</>;
}

export function DiscordPreviewButton<T>({
  queryKey,
  title,
  label,
  ariaLabel,
  description,
  body,
  fetchPreview,
  render,
  disabled,
  disabledReason,
  'data-testid': testId,
  ...buttonProps
}: DiscordPreviewButtonProps<T>) {
  const { t } = useTranslation('discordPreview');
  const [open, setOpen] = useState(false);
  const [openCount, setOpenCount] = useState(0);
  const pendingNavigation = useRef<(() => void) | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(
    () => () => {
      pendingNavigation.current = null;
    },
    [],
  );

  const onOpenChange = (next: boolean) => {
    if (next) {
      pendingNavigation.current = null;
      setOpenCount((n) => n + 1);
    }
    setOpen(next);
  };

  const controls: DiscordPreviewRenderControls = {
    closeAndThen: (callback) => {
      pendingNavigation.current = callback;
      setOpen(false);
    },
  };

  const button = (
    <SecondaryButton
      size="sm"
      {...buttonProps}
      ref={triggerRef}
      data-testid={testId}
      aria-label={ariaLabel ?? t('button.aria', { title })}
      disabled={disabled}
      onClick={() => onOpenChange(true)}
      type="button"
    >
      <Eye aria-hidden="true" />
      {label ?? t('button.label')}
    </SecondaryButton>
  );

  return (
    <>
      {disabled && disabledReason ? (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                data-testid="discord-preview-disabled-trigger"
                tabIndex={0}
                className="inline-flex"
              >
                {button}
              </span>
            </TooltipTrigger>
            <TooltipContent>{disabledReason}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ) : (
        button
      )}
      <InfoDialog
        open={open}
        onOpenChange={onOpenChange}
        onCloseAutoFocus={(event) => {
          const navigate = pendingNavigation.current;
          pendingNavigation.current = null;
          event.preventDefault();
          if (navigate) navigate();
          else triggerRef.current?.focus();
        }}
        title={title}
        description={description ?? t('dialog.description')}
        closeLabel={t('dialog.close')}
        size="lg"
        data-testid="discord-preview-dialog"
      >
        <div className="space-y-3">
          {body}
          {open && fetchPreview && render ? (
            <PreviewResult
              key={openCount}
              queryKey={[...queryKey, openCount]}
              fetchPreview={fetchPreview}
              render={render}
              controls={controls}
            />
          ) : null}
        </div>
      </InfoDialog>
    </>
  );
}
