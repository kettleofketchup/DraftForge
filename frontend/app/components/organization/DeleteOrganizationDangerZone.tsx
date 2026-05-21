import { useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';

import { deleteOrganization } from '~/components/api/orgAPI';
import { ConfirmButton } from '~/components/ui/buttons';
import { DeleteDialog } from '~/components/ui/dialogs';
import { extractApiError } from '~/lib/apiError';
import type { OrganizationType } from './schemas';

export interface DeleteOrganizationDangerZoneProps {
  organization: OrganizationType;
}

export function DeleteOrganizationDangerZone({ organization }: DeleteOrganizationDangerZoneProps) {
  const [showDelete, setShowDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const navigate = useNavigate();

  async function handleDelete() {
    if (!organization.pk) return;
    setIsDeleting(true);
    try {
      await deleteOrganization(organization.pk);
      toast.success(`Organization "${organization.name}" deleted`);
      setShowDelete(false);
      navigate('/organizations');
    } catch (err) {
      const message =
        extractApiError(err) ??
        (err instanceof Error ? err.message : 'Failed to delete organization');
      toast.error(message);
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <section
      data-testid="org-danger-zone"
      className="mt-12 rounded-lg border border-destructive/40 bg-base-900/40 p-6"
    >
      <h2 className="text-lg font-semibold text-destructive">Danger Zone</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Deleting an organization is permanent and removes all of its leagues, events, members,
        and historical data. Only the organization owner can perform this action.
      </p>
      <div className="mt-4">
        <ConfirmButton
          variant="destructive"
          onClick={() => setShowDelete(true)}
          data-testid="org-danger-zone-trigger"
        >
          Delete Organization
        </ConfirmButton>
      </div>

      <DeleteDialog
        open={showDelete}
        onOpenChange={setShowDelete}
        entityKind="Organization"
        entityName={organization.name}
        description={
          <>
            This permanently deletes <strong>{organization.name}</strong>, all of its leagues,
            events, members, and historical data. This cannot be undone.
          </>
        }
        isLoading={isDeleting}
        onConfirm={handleDelete}
        contentTestId="delete-organization-dialog"
        inputTestId="delete-organization-confirm-input"
        confirmTestId="delete-organization-confirm"
        cancelTestId="delete-organization-cancel"
      />
    </section>
  );
}
