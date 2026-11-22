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
import { useUserStore } from '~/store/userStore';
import { MmrStatusBadge } from './MmrStatusBadge';
import { useCreateMmrRequest } from './queries';
import {
  firstFieldError,
  readReviewError,
  requestErrorMessage,
  screenshotErrorMessage,
} from './reviewErrors';
import {
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

function applyServerError(error: unknown, form: Form): void {
  const { status, data } = readReviewError(error);

  if (status === 409 && data.error === 'pending_exists') {
    form.setError('root.server', {
      message: 'You already have a pending request for this',
    });
    return;
  }
  if (status === 413) {
    form.setError('screenshot', {
      message: screenshotErrorMessage('too_large'),
    });
    return;
  }
  if (status === 400) {
    const screenshot = firstFieldError(data.screenshot);
    const mmr = firstFieldError(data.requested_mmr);
    const note = firstFieldError(data.note);
    if (screenshot) {
      form.setError('screenshot', {
        message: screenshotErrorMessage(screenshot),
      });
    }
    if (mmr) form.setError('requested_mmr', { message: mmr });
    if (note) form.setError('note', { message: note });
    if (screenshot || mmr || note) return;
  }
  toast.error(requestErrorMessage(error, 'Could not send the request'));
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
              <FormControl>
                <ScreenshotInput
                  value={field.value ?? null}
                  onChange={(file) => {
                    field.onChange(file ?? undefined);
                    if (file) form.clearErrors('screenshot');
                  }}
                  required
                  error={fieldState.error?.message}
                />
              </FormControl>
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
