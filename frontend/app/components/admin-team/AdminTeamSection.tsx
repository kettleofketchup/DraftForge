/**
 * Admin Team management section for organizations and leagues.
 * Provides UI for managing owner, admins, and staff.
 * Uses AddUserModal for searching and adding users.
 *
 * For organizations, reads from Zustand orgStore.currentOrg for live updates
 * and uses optimistic Zustand + TanStack Query cache updates on mutations.
 * For leagues, relies on onUpdate callback for parent refetch.
 */

import {
  useMutation,
  useMutationState,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import {
  ChevronDown,
  ChevronRight,
  Crown,
  Loader2,
  Megaphone,
  Plus,
  Shield,
  User,
  X,
} from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import { toast } from 'sonner';
import type { AddMemberPayload } from '~/components/api/api';
import {
  addLeagueAdmin,
  addLeagueStaff,
  addOrgAdmin,
  addOrgPromoter,
  addOrgStaff,
  getOrgPromoters,
  removeLeagueAdmin,
  removeLeagueStaff,
  removeOrgAdmin,
  removeOrgPromoter,
  removeOrgStaff,
  transferOrgOwnership,
} from '~/components/api/api';
import type { LeagueType } from '~/components/league/schemas';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import type { OrganizationType } from '~/components/organization/schemas';
import { Button } from '~/components/ui/button';
import { SecondaryButton } from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { AddUserModal } from '~/components/user/AddUserModal';
import { DisplayName } from '~/components/user/avatar';
import type { UserType } from '~/components/user/types';
import { UserAvatar } from '~/components/user/UserAvatar';
import { promotionKeys, useOrgFeatureAccess } from '~/features/org-features';
import {
  useIsLeagueAdmin,
  useIsOrganizationAdmin,
  useIsOrganizationOwner,
  useIsSuperuser,
} from '~/hooks/usePermissions';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { useOrgStore } from '~/store/orgStore';

const log = getLogger('AdminTeamSection');

// Domain 4xx responses ("already a promoter", "not a promoter") are expected races, not faults.
function logPromoterFailure(
  message: string,
  context: Record<string, unknown>,
  err: unknown,
): void {
  const status = (err as { response?: { status?: number } })?.response?.status;
  if (status != null && status >= 400 && status < 500) {
    log.warn(message, { ...context, status, err });
  } else {
    log.error(message, { ...context, err });
  }
}

interface AdminTeamSectionProps {
  organization?: OrganizationType | null;
  league?: LeagueType | null;
  onUpdate?: () => void;
}

interface UserRowProps {
  user: UserType;
  role: 'owner' | 'admin' | 'staff' | 'promoter';
  canRemove: boolean;
  canTransfer?: boolean;
  onRemove?: () => void;
  onTransfer?: () => void;
  isRemoving?: boolean;
}

function UserRow({
  user,
  role,
  canRemove,
  canTransfer,
  onRemove,
  onTransfer,
  isRemoving,
}: UserRowProps) {
  const roleIcon = {
    owner: <Crown className="h-4 w-4 text-yellow-500" />,
    admin: <Shield className="h-4 w-4 text-blue-500" />,
    staff: <User className="h-4 w-4 text-gray-500" />,
    promoter: <Megaphone className="h-4 w-4 text-primary" />,
  };

  return (
    <div
      className="flex items-center justify-between py-2 px-3 bg-base-200 rounded-lg"
      data-testid={`team-member-${user.username}`}
    >
      <div className="flex items-center gap-3">
        {roleIcon[role]}
        <UserAvatar user={user} size="md" />
        <span className="font-medium">{DisplayName(user)}</span>
      </div>
      <div className="flex gap-2">
        {canTransfer && onTransfer && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onTransfer}
            className="text-yellow-600"
            title="Transfer ownership"
          >
            Transfer
          </Button>
        )}
        {canRemove && onRemove && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRemove}
            disabled={isRemoving}
            className="text-destructive"
            title="Remove"
            data-testid={`remove-${role}-${user.username}`}
          >
            {isRemoving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <X className="h-4 w-4" />
            )}
          </Button>
        )}
      </div>
    </div>
  );
}

export function AdminTeamSection({
  organization,
  league,
  onUpdate,
}: AdminTeamSectionProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [transferTarget, setTransferTarget] = useState<UserType | null>(null);
  const [showTransferConfirm, setShowTransferConfirm] = useState(false);
  const [showAddAdmin, setShowAddAdmin] = useState(false);
  const [showAddStaff, setShowAddStaff] = useState(false);
  const [showAddPromoter, setShowAddPromoter] = useState(false);

  const queryClient = useQueryClient();
  const isSuperuser = useIsSuperuser();
  const isOrgOwner = useIsOrganizationOwner(organization);
  const isOrgAdmin = useIsOrganizationAdmin(organization);
  const isLeagueAdmin = useIsLeagueAdmin(
    league,
    organization ? [organization] : undefined,
  );

  const isOrgMode = !!organization && !league;
  const entityId = isOrgMode ? organization?.pk : league?.pk;

  // For org mode, subscribe to Zustand currentOrg for immediate optimistic updates.
  // Zustand subscription triggers re-render directly — no prop chain needed.
  const currentOrg = useOrgStore((s) => s.currentOrg);
  const liveOrg =
    isOrgMode && currentOrg?.pk === organization?.pk
      ? currentOrg
      : organization;

  // Derive team members from Zustand (org mode) or league prop
  const owner = isOrgMode ? liveOrg?.owner : null;
  const admins = (isOrgMode ? liveOrg?.admins : league?.admins) || [];
  const staff = (isOrgMode ? liveOrg?.staff : league?.staff) || [];

  // Permissions
  const canManageAdmins = isOrgMode
    ? isOrgOwner || isOrgAdmin || isSuperuser
    : isLeagueAdmin || isSuperuser;
  const canRemoveAdmins = isOrgMode
    ? isOrgOwner || isSuperuser
    : isLeagueAdmin || isSuperuser;
  const canManageStaff = canManageAdmins;
  const canTransferOwnership = isOrgMode && (isOrgOwner || isSuperuser);
  const featureAccess = useOrgFeatureAccess(
    isOrgMode ? (liveOrg ?? undefined) : undefined,
  );
  const canManagePromoters =
    isOrgMode && !!entityId && featureAccess.canManagePromoters;
  const promotersKey = useMemo(
    () =>
      [
        ...promotionKeys.all(entityId ?? 0, featureAccess.viewerPk),
        'promoters',
      ] as const,
    [entityId, featureAccess.viewerPk],
  );

  // Helper: optimistically update org in both Zustand store and TanStack Query cache
  const updateOrg = useCallback(
    (updater: (org: OrganizationType) => OrganizationType) => {
      if (!isOrgMode || !entityId) return;
      // Zustand — immediate re-render for this component
      const storeOrg = useOrgStore.getState().currentOrg;
      if (storeOrg && storeOrg.pk === entityId) {
        useOrgStore.getState().setCurrentOrg(updater(storeOrg));
      }
      // TanStack Query cache — propagates to useOrganization consumers
      queryClient.setQueryData(
        organizationQueryKey(entityId),
        (old: OrganizationType | undefined) => (old ? updater(old) : old),
      );
    },
    [isOrgMode, entityId, queryClient],
  );

  // --- Mutations ---

  const addAdminMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      return isOrgMode
        ? addOrgAdmin(entityId, userId)
        : addLeagueAdmin(entityId, userId);
    },
    onSuccess: (user) => {
      toast.success('Admin added');
      updateOrg((org) => ({ ...org, admins: [...(org.admins || []), user] }));
      onUpdate?.();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const removeAdminMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      if (isOrgMode) {
        await removeOrgAdmin(entityId, userId);
      } else {
        await removeLeagueAdmin(entityId, userId);
      }
      return userId;
    },
    onSuccess: (userId) => {
      toast.success('Admin removed');
      updateOrg((org) => ({
        ...org,
        admins: (org.admins || []).filter((a) => a.pk !== userId),
      }));
      onUpdate?.();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const addStaffMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      return isOrgMode
        ? addOrgStaff(entityId, userId)
        : addLeagueStaff(entityId, userId);
    },
    onSuccess: (user) => {
      toast.success('Staff added');
      updateOrg((org) => ({ ...org, staff: [...(org.staff || []), user] }));
      onUpdate?.();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const removeStaffMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      if (isOrgMode) {
        await removeOrgStaff(entityId, userId);
      } else {
        await removeLeagueStaff(entityId, userId);
      }
      return userId;
    },
    onSuccess: (userId) => {
      toast.success('Staff removed');
      updateOrg((org) => ({
        ...org,
        staff: (org.staff || []).filter((s) => s.pk !== userId),
      }));
      onUpdate?.();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const transferOwnershipMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      return transferOrgOwnership(entityId, userId);
    },
    onSuccess: (newOwner) => {
      toast.success('Ownership transferred');
      updateOrg((org) => {
        const updatedAdmins = [
          ...(org.admins || []).filter((a) => a.pk !== newOwner.pk),
          ...(org.owner ? [org.owner] : []),
        ];
        return { ...org, owner: newOwner, admins: updatedAdmins };
      });
      setShowTransferConfirm(false);
      setTransferTarget(null);
      onUpdate?.();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const promotersQuery = useQuery({
    queryKey: promotersKey,
    queryFn: () => getOrgPromoters(entityId!),
    enabled: canManagePromoters,
  });
  const promoters = promotersQuery.data ?? [];

  // AddUserModal toasts the outcome; surface the API message instead of the axios one.
  const addPromoterMutation = useMutation({
    mutationFn: (userId: number) =>
      addOrgPromoter(entityId!, userId).catch((err: unknown) => {
        logPromoterFailure(
          'Failed to add promoter',
          { orgId: entityId, userId },
          err,
        );
        throw new Error(extractApiError(err) ?? 'Failed to add promoter');
      }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: promotersKey }),
  });

  const removePromoterKey = useMemo(
    () => ['removeOrgPromoter', entityId] as const,
    [entityId],
  );
  const removePromoterMutation = useMutation({
    mutationKey: removePromoterKey,
    mutationFn: (userId: number) => removeOrgPromoter(entityId!, userId),
    onSuccess: () => {
      toast.success('Promoter removed');
    },
    onError: (err: unknown, userId) => {
      logPromoterFailure(
        'Failed to remove promoter',
        { orgId: entityId, userId },
        err,
      );
      toast.error(extractApiError(err) ?? 'Failed to remove promoter');
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: promotersKey }),
  });
  const pendingPromoterRemovals = useMutationState({
    filters: { mutationKey: removePromoterKey, status: 'pending' },
    select: (mutation) => mutation.state.variables as number,
  });

  // --- AddUserModal handlers ---

  const adminPkSet = useMemo(() => {
    const pks = new Set<number>();
    if (owner?.pk) pks.add(owner.pk);
    for (const a of admins) {
      if (a.pk) pks.add(a.pk);
    }
    return pks;
  }, [owner, admins]);

  const staffPkSet = useMemo(() => {
    const pks = new Set<number>();
    for (const s of staff) {
      if (s.pk) pks.add(s.pk);
    }
    return pks;
  }, [staff]);

  const handleAddAdmin = useCallback(
    async (payload: AddMemberPayload): Promise<UserType> => {
      if (!payload.user_id) throw new Error('User ID required');
      return addAdminMutation.mutateAsync(payload.user_id);
    },
    [addAdminMutation.mutateAsync],
  );

  const handleAddStaff = useCallback(
    async (payload: AddMemberPayload): Promise<UserType> => {
      if (!payload.user_id) throw new Error('User ID required');
      return addStaffMutation.mutateAsync(payload.user_id);
    },
    [addStaffMutation.mutateAsync],
  );

  const isAdminAdded = useCallback(
    (user: UserType) => user.pk != null && adminPkSet.has(user.pk),
    [adminPkSet],
  );

  const isStaffAdded = useCallback(
    (user: UserType) => user.pk != null && staffPkSet.has(user.pk),
    [staffPkSet],
  );

  const promoterPkSet = useMemo(
    () => new Set(promoters.flatMap((p) => (p.pk != null ? [p.pk] : []))),
    [promoters],
  );

  const handleAddPromoter = useCallback(
    async (payload: AddMemberPayload): Promise<UserType> => {
      if (!payload.user_id) throw new Error('User ID required');
      return addPromoterMutation.mutateAsync(payload.user_id);
    },
    [addPromoterMutation.mutateAsync],
  );

  const isPromoterAdded = useCallback(
    (user: UserType) => user.pk != null && promoterPkSet.has(user.pk),
    [promoterPkSet],
  );

  const handleTransferClick = (user: UserType) => {
    setTransferTarget(user);
    setShowTransferConfirm(true);
  };

  const confirmTransfer = async () => {
    if (transferTarget?.pk) {
      // onError already toasts; swallow so ConfirmDialog can close cleanly.
      await transferOwnershipMutation
        .mutateAsync(transferTarget.pk)
        .catch(() => undefined);
    }
  };

  const entityContext = useMemo(() => {
    if (isOrgMode && organization?.pk) {
      return { orgId: organization.pk };
    }
    if (league?.pk) {
      return { orgId: league.organization?.pk, leagueId: league.pk };
    }
    return {};
  }, [isOrgMode, organization, league]);

  if (!entityId) return null;

  return (
    <div className="border border-base-300 rounded-lg overflow-hidden">
      {/* Header */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 bg-base-200 hover:bg-base-300 transition-colors"
      >
        <span className="font-semibold">Admin Team</span>
        {isExpanded ? (
          <ChevronDown className="h-5 w-5" />
        ) : (
          <ChevronRight className="h-5 w-5" />
        )}
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="p-4 space-y-6">
          {/* Owner Section (Organization only) */}
          {isOrgMode && (
            <div>
              <h4 className="font-medium mb-2 flex items-center gap-2">
                <Crown className="h-4 w-4 text-yellow-500" />
                Owner
              </h4>
              {owner ? (
                <UserRow
                  user={owner}
                  role="owner"
                  canRemove={false}
                  canTransfer={false}
                />
              ) : (
                <p className="text-sm text-gray-500 italic">No owner set</p>
              )}
            </div>
          )}

          {/* Inherited Organization Note (League only) */}
          {!isOrgMode && league?.organization && (
            <div className="text-sm text-gray-500 bg-base-200 p-3 rounded-lg">
              <p className="font-medium mb-1">Inherited permissions from:</p>
              <ul className="list-disc list-inside">
                <li>{league.organization.name}</li>
              </ul>
            </div>
          )}

          {/* Admins Section */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-medium flex items-center gap-2">
                <Shield className="h-4 w-4 text-blue-500" />
                Admins
              </h4>
              {canManageAdmins && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setShowAddAdmin(true)}
                  data-testid="add-admin-btn"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Admin
                </Button>
              )}
            </div>
            <div className="space-y-2">
              {admins.length > 0 ? (
                admins.map((admin) => (
                  <UserRow
                    key={admin.pk}
                    user={admin}
                    role="admin"
                    canRemove={canRemoveAdmins}
                    canTransfer={canTransferOwnership}
                    onRemove={() =>
                      admin.pk && removeAdminMutation.mutate(admin.pk)
                    }
                    onTransfer={() => handleTransferClick(admin)}
                    isRemoving={removeAdminMutation.isPending}
                  />
                ))
              ) : (
                <p className="text-sm text-gray-500 italic">No admins</p>
              )}
            </div>
          </div>

          {/* Staff Section */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-medium flex items-center gap-2">
                <User className="h-4 w-4 text-gray-500" />
                Staff
              </h4>
              {canManageStaff && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setShowAddStaff(true)}
                  data-testid="add-staff-btn"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Staff
                </Button>
              )}
            </div>
            <div className="space-y-2">
              {staff.length > 0 ? (
                staff.map((member) => (
                  <UserRow
                    key={member.pk}
                    user={member}
                    role="staff"
                    canRemove={canManageStaff}
                    onRemove={() =>
                      member.pk && removeStaffMutation.mutate(member.pk)
                    }
                    isRemoving={removeStaffMutation.isPending}
                  />
                ))
              ) : (
                <p className="text-sm text-gray-500 italic">No staff</p>
              )}
            </div>
          </div>

          {canManagePromoters && (
            <div data-testid="promoters-section">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-medium flex items-center gap-2">
                  <Megaphone className="h-4 w-4 text-primary" />
                  Promoters
                </h4>
                <SecondaryButton
                  type="button"
                  size="sm"
                  onClick={() => setShowAddPromoter(true)}
                  data-testid="add-promoter-btn"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Promoter
                </SecondaryButton>
              </div>
              <div className="space-y-2">
                {promotersQuery.isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                ) : promotersQuery.isError ? (
                  <p
                    className="text-sm text-destructive"
                    data-testid="promoters-error"
                  >
                    {extractApiError(promotersQuery.error) ??
                      'Failed to load promoters'}
                  </p>
                ) : promoters.length > 0 ? (
                  promoters.map((promoter) => (
                    <UserRow
                      key={promoter.pk}
                      user={promoter}
                      role="promoter"
                      canRemove
                      onRemove={() =>
                        promoter.pk &&
                        removePromoterMutation.mutate(promoter.pk)
                      }
                      isRemoving={
                        promoter.pk != null &&
                        pendingPromoterRemovals.includes(promoter.pk)
                      }
                    />
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    No promoters
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={showTransferConfirm && !!transferTarget}
        onOpenChange={(open) => {
          setShowTransferConfirm(open);
          if (!open) setTransferTarget(null);
        }}
        title="Transfer Ownership"
        description={
          <>
            Are you sure you want to transfer ownership to{' '}
            <strong>
              {transferTarget?.guildNickname ||
                transferTarget?.discordNickname ||
                transferTarget?.username}
            </strong>
            ? You will become an admin after the transfer.
          </>
        }
        confirmLabel="Transfer"
        variant="warning"
        isLoading={transferOwnershipMutation.isPending}
        onConfirm={confirmTransfer}
      />

      {/* Add Admin Modal */}
      {canManageAdmins && (
        <AddUserModal
          open={showAddAdmin}
          onOpenChange={setShowAddAdmin}
          title={
            isOrgMode
              ? `Add Admin to ${organization?.name || 'Organization'}`
              : `Add Admin to ${league?.name || 'League'}`
          }
          entityContext={entityContext}
          onAdd={handleAddAdmin}
          isAdded={isAdminAdded}
          hasDiscordServer={false}
        />
      )}

      {/* Add Staff Modal */}
      {canManageStaff && (
        <AddUserModal
          open={showAddStaff}
          onOpenChange={setShowAddStaff}
          title={
            isOrgMode
              ? `Add Staff to ${organization?.name || 'Organization'}`
              : `Add Staff to ${league?.name || 'League'}`
          }
          entityContext={entityContext}
          onAdd={handleAddStaff}
          isAdded={isStaffAdded}
          hasDiscordServer={false}
        />
      )}

      {canManagePromoters && (
        <AddUserModal
          open={showAddPromoter}
          onOpenChange={setShowAddPromoter}
          title={`Add Promoter to ${organization?.name || 'Organization'}`}
          entityContext={entityContext}
          onAdd={handleAddPromoter}
          isAdded={isPromoterAdded}
          hasDiscordServer={false}
        />
      )}
    </div>
  );
}
