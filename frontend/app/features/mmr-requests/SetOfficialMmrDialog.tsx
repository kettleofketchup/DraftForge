import { zodResolver } from '@hookform/resolvers/zod';
import { Check, ChevronsUpDown } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { toast } from 'sonner';
import type { z } from 'zod';
import {
  GAME_LABEL,
  GAME_TYPES,
  LEAGUE_MMR_GAME,
  type GameTypeValue,
} from '~/components/game/constants';
import { Button } from '~/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '~/components/ui/command';
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
import { Label } from '~/components/ui/label';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '~/components/ui/popover';
import { RadioGroup, RadioGroupItem } from '~/components/ui/radio-group';
import { Textarea } from '~/components/ui/textarea';
import { DisplayName } from '~/components/user/avatar';
import { useLeagueUsers } from '~/hooks/useLeagueUsers';
import { useOrgUsers } from '~/hooks/useOrgUsers';
import { cn } from '~/lib/utils';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { MmrStatusBadge } from './MmrStatusBadge';
import { useStaffSetMmr, useUserMmrSummary } from './queries';
import type { MmrScope } from './queryKeys';
import {
  firstFieldError,
  readReviewError,
  reviewErrorMessage,
  screenshotErrorMessage,
} from './reviewErrors';
import {
  staffSetFormSchema,
  TEXT_MAX_LENGTH,
  type StaffSetFormSchema,
  type StaffSetFormValues,
  type StaffSetMmrInput,
  type UserMmrSummary,
} from './schemas';
import { ScreenshotInput } from './ScreenshotInput';

export interface SetOfficialMember {
  userPk: number;
  orgUserPk?: number;
  leagueUserPk?: number;
  name: string;
}

export interface SetOfficialMmrDialogProps {
  scope: MmrScope;
  member?: SetOfficialMember;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface TargetOption {
  key: string;
  label: string;
  gameType: GameTypeValue;
  current: number;
  verified: boolean;
  input:
    | { target: 'org'; orgUserPk: number; gameType: number }
    | { target: 'league'; leagueUserPk: number };
}

type FormInput = z.input<StaffSetFormSchema>;
type StaffForm = UseFormReturn<FormInput, unknown, StaffSetFormValues>;

const EMPTY_VALUES: FormInput = { mmr: '', screenshot: null, note: '' };

function buildTargets(
  scope: MmrScope,
  member: SetOfficialMember,
  summary: UserMmrSummary | undefined,
): TargetOption[] {
  const options: TargetOption[] = [];
  if ('org' in scope) {
    const orgEntry = summary?.orgs.find((o) => o.organization.pk === scope.org);
    const orgUserPk = member.orgUserPk ?? orgEntry?.org_user_pk ?? null;
    if (orgUserPk != null) {
      for (const game of GAME_TYPES) {
        const row = orgEntry?.game_mmrs.find((g) => g.game_type === game);
        options.push({
          key: `org-${game}`,
          label: `Org MMR · ${GAME_LABEL[game]}`,
          gameType: game,
          current: row?.mmr ?? 0,
          verified: row?.verified ?? false,
          input: { target: 'org', orgUserPk, gameType: game },
        });
      }
    }
  }
  for (const entry of summary?.leagues ?? []) {
    const inScope =
      'org' in scope
        ? entry.organization_pk === scope.org
        : entry.league.pk === scope.league;
    const leagueUserPk =
      'league' in scope && member.leagueUserPk != null
        ? member.leagueUserPk
        : entry.league_user_pk;
    if (!inScope || leagueUserPk == null) continue;
    options.push({
      key: `league-${entry.league.pk}`,
      label: `League · ${entry.league.name}`,
      gameType: LEAGUE_MMR_GAME,
      current: entry.mmr,
      verified: entry.verified,
      input: { target: 'league', leagueUserPk },
    });
  }
  if (
    'league' in scope &&
    member.leagueUserPk != null &&
    !options.some((o) => o.key === `league-${scope.league}`)
  ) {
    options.push({
      key: `league-${scope.league}`,
      label: 'League MMR',
      gameType: LEAGUE_MMR_GAME,
      current: 0,
      verified: false,
      input: { target: 'league', leagueUserPk: member.leagueUserPk },
    });
  }
  return options;
}

function applyServerError(error: unknown, form: StaffForm): void {
  const { status, data } = readReviewError(error);
  if (status === 413) {
    form.setError('screenshot', {
      message: screenshotErrorMessage('too_large'),
    });
    return;
  }
  if (status === 400) {
    const screenshot = firstFieldError(data.screenshot);
    const mmr = firstFieldError(data.mmr);
    const note = firstFieldError(data.note);
    if (screenshot) {
      form.setError('screenshot', {
        message: screenshotErrorMessage(screenshot),
      });
    }
    if (mmr) form.setError('mmr', { message: mmr });
    if (note) form.setError('note', { message: note });
    if (screenshot || mmr || note) return;
  }
  toast.error(reviewErrorMessage(error, 'Could not set the official MMR'));
}

function useScopeMembers(scope: MmrScope, open: boolean, enabled: boolean) {
  const orgId = 'org' in scope ? scope.org : 0;
  const leagueId = 'league' in scope ? scope.league : 0;
  const orgUsers = useOrgUsers(orgId);
  const leagueUsers = useLeagueUsers(leagueId);
  useEffect(() => {
    if (!open || !enabled) return;
    if (orgId) void useOrgStore.getState().getOrgUsers(orgId);
    if (leagueId) void useLeagueStore.getState().getLeagueUsers(leagueId);
  }, [open, enabled, orgId, leagueId]);
  return 'org' in scope ? orgUsers : leagueUsers;
}

interface MemberPickerProps {
  scope: MmrScope;
  open: boolean;
  value: SetOfficialMember | null;
  onChange: (member: SetOfficialMember) => void;
}

function MemberPicker({ scope, open, value, onChange }: MemberPickerProps) {
  const [popoverOpen, setPopoverOpen] = useState(false);
  const users = useScopeMembers(scope, open, true);

  return (
    <div className="flex flex-col gap-2">
      <Label>Member</Label>
      <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={popoverOpen}
            className="w-full justify-between"
            data-testid="set-official-mmr-member"
          >
            <span className="truncate">
              {value ? value.name : 'Choose a member…'}
            </span>
            <ChevronsUpDown className="opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-(--radix-popover-trigger-width) p-0">
          <Command>
            <CommandInput
              placeholder="Search members…"
              className="h-9"
              data-testid="set-official-mmr-member-search"
            />
            <CommandList>
              <CommandEmpty>No members found</CommandEmpty>
              <CommandGroup>
                {users.map((user) => {
                  const name = DisplayName(user);
                  return (
                    <CommandItem
                      key={user.pk}
                      value={`${name} ${user.username ?? ''} ${user.pk}`}
                      data-testid={`set-official-mmr-member-${user.pk}`}
                      onSelect={() => {
                        onChange({ userPk: user.pk, name });
                        setPopoverOpen(false);
                      }}
                    >
                      {name}
                      <Check
                        className={cn(
                          'ml-auto',
                          value?.userPk === user.pk
                            ? 'opacity-100'
                            : 'opacity-0',
                        )}
                      />
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}

export function SetOfficialMmrDialog({
  scope,
  member,
  open,
  onOpenChange,
}: SetOfficialMmrDialogProps) {
  const [picked, setPicked] = useState<SetOfficialMember | null>(null);
  const subject = member ?? picked;
  const summary = useUserMmrSummary(open ? subject?.userPk : null);
  const targets = useMemo(
    () => (subject ? buildTargets(scope, subject, summary.data) : []),
    [scope, subject, summary.data],
  );
  const [targetKey, setTargetKey] = useState<string | null>(null);
  const target = targets.find((t) => t.key === targetKey) ?? targets[0] ?? null;
  const staffSet = useStaffSetMmr(scope);

  const schema = useMemo(
    () => staffSetFormSchema(target?.gameType ?? LEAGUE_MMR_GAME),
    [target?.gameType],
  );
  const form: StaffForm = useForm<FormInput, unknown, StaffSetFormValues>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY_VALUES,
  });

  useEffect(() => {
    if (open) {
      form.reset(EMPTY_VALUES);
      setTargetKey(null);
      setPicked(null);
    }
  }, [open, form]);

  const onSubmit = async (values: StaffSetFormValues) => {
    if (!subject || !target) {
      toast.error('Choose a member and a target first');
      return;
    }
    const input: StaffSetMmrInput = {
      ...target.input,
      mmr: values.mmr,
      screenshot: values.screenshot ?? null,
      note: values.note,
    } as StaffSetMmrInput;
    try {
      await staffSet.mutateAsync({ ...input, subjectPk: subject.userPk });
      toast.success(`${subject.name}'s ${target.label} is now ${values.mmr}`);
      onOpenChange(false);
    } catch (error) {
      applyServerError(error, form);
    }
  };

  const noTargets =
    subject != null && !summary.isLoading && targets.length === 0;

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={member ? `Set official MMR — ${member.name}` : 'Set official MMR'}
      description="The value becomes official immediately and replaces any pending request for the same target. A screenshot is optional."
      submitLabel="Set official MMR"
      isSubmitting={staffSet.isPending}
      onSubmit={form.handleSubmit(onSubmit)}
      submitTestId="set-official-mmr-submit"
      data-testid="set-official-mmr-dialog"
    >
      <Form {...form}>
        {!member && (
          <MemberPicker
            scope={scope}
            open={open}
            value={picked}
            onChange={(next) => {
              setPicked(next);
              setTargetKey(null);
            }}
          />
        )}

        {subject && targets.length > 0 && (
          <div className="flex flex-col gap-2">
            <Label>Target</Label>
            <RadioGroup
              value={target?.key ?? ''}
              onValueChange={setTargetKey}
              data-testid="set-official-mmr-target"
            >
              {targets.map((option) => (
                <div key={option.key} className="flex items-center gap-2">
                  <RadioGroupItem
                    value={option.key}
                    id={`set-official-mmr-target-${option.key}`}
                    data-testid={`set-official-mmr-target-${option.key}`}
                  />
                  <Label
                    htmlFor={`set-official-mmr-target-${option.key}`}
                    className="flex flex-wrap items-center gap-2 font-normal"
                  >
                    {option.label}
                    <span className="text-muted-foreground">
                      {option.current > 0 ? option.current : 'Not set'}
                    </span>
                    {option.current > 0 && (
                      <MmrStatusBadge verified={option.verified} />
                    )}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          </div>
        )}

        {noTargets && (
          <p
            role="alert"
            className="text-sm text-muted-foreground"
            data-testid="set-official-mmr-no-targets"
          >
            This member has no membership here to set an MMR for.
          </p>
        )}

        <FormField
          control={form.control}
          name="mmr"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Official MMR</FormLabel>
              <FormControl>
                <Input
                  type="number"
                  inputMode="numeric"
                  placeholder="e.g. 4800"
                  data-testid="set-official-mmr-value"
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
              <FormLabel>Screenshot (optional)</FormLabel>
              <FormControl>
                <ScreenshotInput
                  value={field.value ?? null}
                  onChange={(file) => {
                    field.onChange(file);
                    if (file) form.clearErrors('screenshot');
                  }}
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
                  data-testid="set-official-mmr-note"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </Form>
    </FormDialog>
  );
}
