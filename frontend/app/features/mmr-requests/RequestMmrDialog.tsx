import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useMemo } from 'react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { toast } from 'sonner';
import type { z } from 'zod';
import {
  GAME_LABEL,
  LEAGUE_MMR_GAME,
  toGameType,
} from '~/components/game/constants';
import { FormDialog } from '~/components/ui/dialogs';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Textarea } from '~/components/ui/textarea';
import { extractApiError } from '~/lib/apiError';
import { useUserStore } from '~/store/userStore';
import { MmrStatusBadge } from './MmrStatusBadge';
import { useCreateMmrRequest } from './queries';
import {
  MAX_SCREENSHOT_BYTES,
  requestMmrFormSchema,
  TEXT_MAX_LENGTH,
  type CreateMmrRequestInput,
  type RequestMmrFormSchema,
  type RequestMmrFormValues,
} from './schemas';
import { ScreenshotInput } from './ScreenshotInput';

export type RequestTarget =
  | {
      kind: 'org';
      orgUserPk: number;
      orgName: string;
      gameType: number;
      current: number;
      currentVerified: boolean;
    }
  | {
      kind: 'league';
      leagueUserPk: number;
      leagueName: string;
      orgName?: string;
      current: number;
      currentVerified: boolean;
    };

export interface RequestMmrDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  target: RequestTarget;
}

type FormInput = z.input<RequestMmrFormSchema>;
type Form = UseFormReturn<FormInput, unknown, RequestMmrFormValues>;

const SCREENSHOT_MESSAGES: Record<string, string> = {
  too_large: `The image must be ${MAX_SCREENSHOT_BYTES / (1024 * 1024)} MB or smaller.`,
  unsupported_type: 'Use a PNG, JPEG or WebP image.',
  invalid_image: "That file isn't a readable image.",
};

const TOAST_MESSAGES: Record<number, string> = {
  429: "You've sent too many requests. Try again later.",
  503: 'The server is busy processing images. Try again in a moment.',
  507: 'Uploads are unavailable right now. Try again later.',
};

interface HttpErrorShape {
  response?: { status?: number; data?: unknown };
}

function firstMessage(value: unknown): string | null {
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
  return typeof value === 'string' ? value : null;
}

function applyServerError(error: unknown, form: Form): void {
  const response = (error as HttpErrorShape)?.response;
  const status = response?.status;
  const data =
    response?.data && typeof response.data === 'object'
      ? (response.data as Record<string, unknown>)
      : {};

  if (status === 409 && data.error === 'pending_exists') {
    form.setError('root.server', {
      message: 'You already have a pending request for this',
    });
    return;
  }
  if (status === 413) {
    form.setError('screenshot', { message: SCREENSHOT_MESSAGES.too_large });
    return;
  }
  if (status === 400) {
    const screenshot = firstMessage(data.screenshot);
    const mmr = firstMessage(data.requested_mmr);
    const note = firstMessage(data.note);
    if (screenshot) {
      form.setError('screenshot', {
        message: SCREENSHOT_MESSAGES[screenshot] ?? screenshot,
      });
    }
    if (mmr) form.setError('requested_mmr', { message: mmr });
    if (note) form.setError('note', { message: note });
    if (screenshot || mmr || note) return;
  }
  toast.error(
    (status != null && TOAST_MESSAGES[status]) ||
      extractApiError(error) ||
      'Could not send the request',
  );
}

function targetTitle(target: RequestTarget): string {
  return target.kind === 'org'
    ? `${target.orgName} · ${GAME_LABEL[toGameType(target.gameType)]}`
    : `${target.leagueName} (league)`;
}

function targetHelp(target: RequestTarget): string {
  if (target.kind === 'org') {
    return `Org MMR is your default rating in ${target.orgName}. League MMR is set separately for each league.`;
  }
  const league = `League MMR is the value used for seeding in ${target.leagueName}.`;
  return target.orgName
    ? `Org MMR is your default rating in ${target.orgName}. ${league}`
    : league;
}

function toInput(
  target: RequestTarget,
  values: RequestMmrFormValues,
): CreateMmrRequestInput {
  const common = {
    requestedMmr: values.requested_mmr,
    screenshot: values.screenshot,
    note: values.note,
  };
  return target.kind === 'org'
    ? {
        target: 'org',
        orgUserPk: target.orgUserPk,
        gameType: target.gameType,
        ...common,
      }
    : { target: 'league', leagueUserPk: target.leagueUserPk, ...common };
}

export function RequestMmrDialog({
  open,
  onOpenChange,
  target,
}: RequestMmrDialogProps) {
  const viewerPk = useUserStore((state) => state.currentUser?.pk ?? 0);
  const create = useCreateMmrRequest(viewerPk);
  const gameType =
    target.kind === 'org' ? toGameType(target.gameType) : LEAGUE_MMR_GAME;
  const schema = useMemo(() => requestMmrFormSchema(gameType), [gameType]);
  const form: Form = useForm<FormInput, unknown, RequestMmrFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { requested_mmr: '', note: '' },
  });

  useEffect(() => {
    if (open) form.reset({ requested_mmr: '', note: '' });
  }, [open, form]);

  const onSubmit = async (values: RequestMmrFormValues) => {
    form.clearErrors('root.server');
    try {
      await create.mutateAsync(toInput(target, values));
      toast.success('MMR update requested');
      onOpenChange(false);
    } catch (error) {
      applyServerError(error, form);
    }
  };

  const serverError = form.formState.errors.root?.server?.message;

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Request MMR update — ${targetTitle(target)}`}
      description={targetHelp(target)}
      submitLabel="Submit request"
      isSubmitting={create.isPending}
      onSubmit={form.handleSubmit(onSubmit)}
      submitTestId="mmr-request-submit"
      data-testid="mmr-request-dialog"
    >
      <Form {...form}>
        <p
          className="flex flex-wrap items-center gap-2 text-sm"
          data-testid="mmr-request-current"
        >
          <span className="text-muted-foreground">Current:</span>
          <span className="font-medium">
            {target.current > 0 ? target.current : 'Not set'}
          </span>
          {target.current > 0 && (
            <MmrStatusBadge verified={target.currentVerified} />
          )}
        </p>

        <FormField
          control={form.control}
          name="requested_mmr"
          render={({ field }) => (
            <FormItem>
              <FormLabel>New MMR</FormLabel>
              <FormControl>
                <Input
                  type="number"
                  inputMode="numeric"
                  placeholder="e.g. 4800"
                  data-testid="mmr-request-value"
                  name={field.name}
                  ref={field.ref}
                  onBlur={field.onBlur}
                  value={
                    typeof field.value === 'number' ||
                    typeof field.value === 'string'
                      ? field.value
                      : ''
                  }
                  onChange={(e) =>
                    field.onChange(
                      e.target.value === '' ? '' : e.target.valueAsNumber,
                    )
                  }
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="screenshot"
          render={({ field, fieldState }) => (
            <FormItem>
              <FormLabel>Screenshot *</FormLabel>
              <ScreenshotInput
                value={field.value ?? null}
                onChange={(file) => {
                  field.onChange(file ?? undefined);
                  if (file) form.clearErrors('screenshot');
                }}
                required
                error={fieldState.error?.message}
              />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="note"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Note</FormLabel>
              <FormControl>
                <Textarea
                  rows={2}
                  maxLength={TEXT_MAX_LENGTH}
                  placeholder="Optional"
                  data-testid="mmr-request-note"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {serverError && (
          <p
            role="alert"
            className="text-sm text-destructive"
            data-testid="mmr-request-error"
          >
            {serverError}
          </p>
        )}
      </Form>
    </FormDialog>
  );
}
