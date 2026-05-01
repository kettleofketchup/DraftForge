import React, { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import type { UserClassType } from '~/components/user/types';
import { EditIconButton } from '~/components/ui/buttons';
import { FormDialog } from '~/components/ui/dialogs';
import { Form } from '~/components/ui/form';
import { useUserCacheStore } from '~/store/userCacheStore';
import {
  buildDefaults,
  dispatchPatch,
  EditUserSchema,
  pickDirty,
  scopeToContext,
  useScopedEditPermission,
  type EditableField,
  type EditUserInput,
  type EditUserScope,
} from './editUserSchema';
import { UserEditForm } from './editForm';

interface Props {
  user: UserClassType;
  /** Defaults to global scope so legacy call sites continue compiling
   *  until they're migrated. New code should always pass an explicit scope. */
  scope?: EditUserScope;
  fields?: Partial<Record<EditableField, boolean>>;
}

export function UserEditModal({ user, scope = { kind: 'global' }, fields }: Props) {
  const canEdit = useScopedEditPermission(scope);
  const [open, setOpen] = useState(false);
  const showMmr = scope.kind !== 'global' && (fields?.mmr ?? true);

  const form = useForm<EditUserInput>({
    // Cast: z.coerce produces input=unknown / output=EditUserInput, but we
    // already pass clean numeric defaults from buildDefaults() and the
    // form's NumberField coerces on every keystroke.
    resolver: zodResolver(EditUserSchema) as unknown as import('react-hook-form').Resolver<EditUserInput>,
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
        ? (scope.organization?.pk ?? scope.league.organization?.pk ?? null)
        : null;
  const scopeLeaguePk = scope.kind === 'league' ? scope.league.pk : null;
  useEffect(() => {
    if (open) form.reset(buildDefaults(user, scope));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- scope is read inline; deps cover its identity keys
  }, [open, user.pk, user.orgUserPk, scope.kind, scopeOrgPk, scopeLeaguePk, form]);

  async function onSubmit(data: EditUserInput) {
    if (!isDirty) {
      setOpen(false);
      return;
    }
    try {
      const payload = pickDirty(data, dirtyFields);
      const updated = await dispatchPatch(user, scope, payload);
      useUserCacheStore.getState().upsert([updated], scopeToContext(scope));
      toast.success(`${user.username} updated`);
      setOpen(false);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : `Failed to update ${user.username}`;
      toast.error(message);
    }
  }

  if (!canEdit) return null;

  return (
    <>
      <EditIconButton
        tooltip="Edit User"
        data-testid="edit-user-btn"
        onClick={() => setOpen(true)}
      />
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title={`Edit ${user.nickname || user.username}`}
        description="Update this user's profile."
        submitLabel="Save Changes"
        isSubmitting={isSubmitting}
        onSubmit={form.handleSubmit(onSubmit)}
        size="md"
        data-testid="edit-user-modal"
      >
        <Form {...form}>
          <UserEditForm
            form={form}
            showMmr={showMmr}
            mmrLabel={scope.kind === 'org' ? 'Org MMR' : 'MMR'}
          />
        </Form>
      </FormDialog>
    </>
  );
}

export default UserEditModal;
