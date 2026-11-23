import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import {
  GAME_MMR_HOTKEY,
  mmrTestId,
  type GameTypeValue,
} from '~/components/game/constants';
import { EditIconButton } from '~/components/ui/buttons';
import { FormDialog } from '~/components/ui/dialogs';
import { Form } from '~/components/ui/form';
import { DisplayName } from '~/components/user/avatar';
import type { UserClassType } from '~/components/user/types';
import { extractApiError } from '~/lib/apiError';
import { useUserCacheStore } from '~/store/userCacheStore';
import { UserEditForm } from './editForm';
import {
  buildDefaults,
  dispatchPatch,
  editableGames,
  EditUserSchema,
  pickDirty,
  scopeToContext,
  useScopedEditMode,
  useTournamentEditScope,
  type EditableField,
  type EditUserInput,
  type EditUserScope,
} from './editUserSchema';
import { steamAccountIdConflictFromError } from './steamAccountIdConflict';

interface Props {
  user: UserClassType;
  /** Defaults to global scope so legacy call sites continue compiling
   *  until they're migrated. New code should always pass an explicit scope. */
  scope?: EditUserScope;
  fields?: Partial<Record<EditableField, boolean>>;
}

export function UserEditModal({
  user,
  scope: scopeProp = { kind: 'global' },
  fields,
}: Props) {
  const scope = useTournamentEditScope(scopeProp, user.pk);
  const editMode = useScopedEditMode(scope);
  const canEdit = editMode !== null;
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  // FormDialog stays eagerly mounted — Radix Dialog with `open=false`
  // already hides its DialogContent (it's not in the DOM until the
  // dialog opens), so the per-card cost of having FormDialog in the
  // tree is small. An earlier lazy-mount attempt (gating on a
  // `hasOpened` state) broke Playwright integration tests because
  // Radix Dialog sometimes skips the open transition when mounted
  // already-open — DialogContent stayed hidden and the form inputs
  // weren't visible. The right way to remove the closed-FormDialog
  // render cost is to memoize FormDialog itself (stable props) or
  // to extract the dialog tree into its own React.lazy chunk;
  // tracked as a follow-up.
  const mmrGames = fields?.game_mmrs === false ? [] : editableGames(scope);

  const form = useForm<EditUserInput>({
    // Cast: z.coerce produces input=unknown / output=EditUserInput, but we
    // already pass clean numeric defaults from buildDefaults() and the
    // form's NumberField coerces on every keystroke.
    resolver: zodResolver(
      EditUserSchema,
    ) as unknown as import('react-hook-form').Resolver<EditUserInput>,
    defaultValues: buildDefaults(user, scope),
  });

  // RHF tracks formState properties only when they are read during render.
  // Subscribe to isDirty/dirtyFields here so onSubmit's read returns the
  // up-to-date values (otherwise both stay stuck at their initial state).
  const { isDirty, dirtyFields, isSubmitting } = form.formState;

  // Re-seed when modal opens or the underlying user/scope target changes.
  // Including the entity pk (not the whole scope object literal) lets us
  // detect cross-entity transitions like org A → org B without trusting that
  // callers always close the modal between users.
  const scopeOrgPk =
    scope.kind === 'org'
      ? scope.organization.pk
      : scope.kind === 'league'
        ? (scope.orgId ??
          scope.organization?.pk ??
          scope.league.organization?.pk ??
          null)
        : null;
  const scopeLeaguePk = scope.kind === 'league' ? scope.league.pk : null;
  const scopeGame = scope.kind === 'global' ? null : (scope.gameType ?? null);
  useEffect(() => {
    if (open) form.reset(buildDefaults(user, scope));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- scope is read inline; deps cover its identity keys
  }, [
    open,
    user.pk,
    user.orgUserPk,
    scope.kind,
    scopeOrgPk,
    scopeLeaguePk,
    scopeGame,
    form,
  ]);

  // useCallback so handleSubmit returns a stable wrapper across renders —
  // otherwise FormDialog's onSubmit prop changes every render and forces
  // a re-render of FormDialog (and its dialog content tree) whenever any
  // unrelated state in this component updates. Read isDirty/dirtyFields
  // off form.formState inside the callback so the stable reference still
  // sees the latest RHF state at submit time.
  const onSubmit = React.useCallback(
    async (data: EditUserInput) => {
      const fs = form.formState;
      if (!fs.isDirty) {
        setOpen(false);
        return;
      }
      try {
        const payload = pickDirty(data, fs.dirtyFields);
        const updated = await dispatchPatch(user, scope, payload);
        useUserCacheStore.getState().upsert([updated], scopeToContext(scope));
        if (user.pk) {
          queryClient.invalidateQueries({ queryKey: ['user', user.pk] });
        }
        toast.success(`${DisplayName(user)} updated`);
        setOpen(false);
      } catch (err) {
        const friendIdError = steamAccountIdConflictFromError(
          (err as { response?: { data?: unknown } })?.response?.data,
        );
        if (friendIdError) {
          form.setError('steam_account_id', {
            type: 'server',
            message: friendIdError,
          });
          toast.error(friendIdError);
          return;
        }
        const message =
          extractApiError(err) ??
          (err instanceof Error
            ? err.message
            : `Failed to update ${DisplayName(user)}`);
        toast.error(message);
      }
    },
    [form, user, scope, queryClient],
  );

  // Stable submit handler for FormDialog. form.handleSubmit returns a new
  // function each render, so memoize the composed callback.
  const submitHandler = React.useMemo(
    () => form.handleSubmit(onSubmit),
    [form, onSubmit],
  );

  // Stable open-handler. The inline arrow created a fresh closure each
  // render, which the React Scan trace surfaced as `onClick:16x` on
  // EditIconButton. setOpen from useState is itself stable.
  const handleOpen = React.useCallback(() => setOpen(true), []);

  // Field-focus hotkeys while the modal is open. We dispatch only when focus
  // is outside an editable element, so typing those letters into a real
  // input doesn't yank focus elsewhere. Position keys (Z X C V B) target the
  // SelectTrigger button — focusing it lets the user open the dropdown with
  // Space/Enter and pick with arrow keys, matching shadcn/Radix conventions.
  useEffect(() => {
    if (!open) return;
    const KEY_TO_TESTID: Record<string, string> = {
      ...Object.fromEntries(
        (Object.entries(GAME_MMR_HOTKEY) as [string, string][]).map(
          ([g, key]) => [key, mmrTestId(Number(g) as GameTypeValue)],
        ),
      ),
      n: 'edit-user-nickname',
      f: 'edit-user-steam_account_id',
      z: 'edit-user-carry',
      x: 'edit-user-mid',
      c: 'edit-user-offlane',
      v: 'edit-user-soft_support',
      b: 'edit-user-hard_support',
    };
    const handler = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      const testId = KEY_TO_TESTID[e.key.toLowerCase()];
      if (!testId) return;
      const target = document.querySelector<HTMLElement>(
        `[data-testid="${testId}"]`,
      );
      if (!target) return;
      // Already on the matched element — let the keystroke through.
      if (document.activeElement === target) return;
      // Typing into another editable element — never steal focus.
      const active = document.activeElement as HTMLElement | null;
      const tag = active?.tagName;
      if (
        tag === 'INPUT' ||
        tag === 'TEXTAREA' ||
        tag === 'SELECT' ||
        active?.isContentEditable
      )
        return;
      e.preventDefault();
      target.focus();
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement
      ) {
        // Inputs: select the existing value so typing replaces it.
        target.select();
      } else if (target instanceof HTMLButtonElement) {
        // SelectTrigger buttons: also click to open the dropdown immediately
        // (otherwise the user has to press Space/Enter as a second step).
        target.click();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open]);

  if (!canEdit) return null;

  return (
    <>
      <EditIconButton
        tooltip="Edit User"
        data-testid="edit-user-btn"
        onClick={handleOpen}
      />
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title={`Edit ${DisplayName(user)}`}
        description="Update this user's profile."
        submitLabel="Save Changes"
        isSubmitting={isSubmitting}
        onSubmit={submitHandler}
        size="xl"
        autoFocus={false}
        escapeBlursToContent
        data-testid="edit-user-modal"
      >
        <Form {...form}>
          <UserEditForm
            form={form}
            mmrGames={mmrGames}
            editingUserPk={user.pk}
            mmrOnly={editMode === 'mmr'}
          />
        </Form>
      </FormDialog>
    </>
  );
}

export default UserEditModal;
