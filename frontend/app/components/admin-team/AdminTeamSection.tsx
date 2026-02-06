/**
 * Admin Team management section for organizations and leagues.
 * Provides UI for managing owner, admins, and staff.
 * Uses AddUserModal for searching and adding users.
 * Uses local state to avoid full page re-renders on updates.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Crown, Plus, Shield, User, X } from 'lucide-react';
import { toast } from 'sonner';
import type { UserType } from '~/components/user/types';
import type { OrganizationType } from '~/components/organization/schemas';
import type { LeagueType } from '~/components/league/schemas';
import type { AddMemberPayload } from '~/components/api/api';
import {
  addOrgAdmin,
  removeOrgAdmin,
  addOrgStaff,
  removeOrgStaff,
  transferOrgOwnership,
  addLeagueAdmin,
  removeLeagueAdmin,
  addLeagueStaff,
  removeLeagueStaff,
} from '~/components/api/api';
import {
  useIsOrganizationOwner,
  useIsOrganizationAdmin,
  useIsLeagueAdmin,
  useIsSuperuser,
} from '~/hooks/usePermissions';
import { AddUserModal } from '~/components/user/AddUserModal';
import { Button } from '~/components/ui/button';

interface AdminTeamSectionProps {
  organization?: OrganizationType | null;
  league?: LeagueType | null;
  onUpdate?: () => void;
}

interface UserRowProps {
  user: UserType;
  role: 'owner' | 'admin' | 'staff';
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
  };

  const displayName =
    user.guildNickname || user.discordNickname || user.nickname || user.username;

  return (
    <div className="flex items-center justify-between py-2 px-3 bg-base-200 rounded-lg" data-testid={`team-member-${user.username}`}>
      <div className="flex items-center gap-3">
        {roleIcon[role]}
        <img
          src={user.avatarUrl || user.avatar || '/default-avatar.png'}
          alt={displayName}
          className="w-8 h-8 rounded-full"
        />
        <span className="font-medium">{displayName}</span>
      </div>
      <div className="flex gap-2">
        {canTransfer && onTransfer && (
          <button
            onClick={onTransfer}
            className="btn btn-xs btn-ghost text-yellow-600"
            title="Transfer ownership"
          >
            Transfer
          </button>
        )}
        {canRemove && onRemove && (
          <button
            onClick={onRemove}
            disabled={isRemoving}
            className="btn btn-xs btn-ghost text-error"
            title="Remove"
          >
            {isRemoving ? (
              <span className="loading loading-spinner loading-xs" />
            ) : (
              <X className="h-4 w-4" />
            )}
          </button>
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

  const isSuperuser = useIsSuperuser();
  const isOrgOwner = useIsOrganizationOwner(organization);
  const isOrgAdmin = useIsOrganizationAdmin(organization);
  const isLeagueAdmin = useIsLeagueAdmin(league, organization ? [organization] : undefined);

  const isOrgMode = !!organization && !league;
  const entityId = isOrgMode ? organization?.pk : league?.pk;

  // Local state for team members
  const [localOwner, setLocalOwner] = useState<UserType | null | undefined>(
    isOrgMode ? organization?.owner : null
  );
  const [localAdmins, setLocalAdmins] = useState<UserType[]>(
    (isOrgMode ? organization?.admins : league?.admins) || []
  );
  const [localStaff, setLocalStaff] = useState<UserType[]>(
    (isOrgMode ? organization?.staff : league?.staff) || []
  );

  // Sync local state when props change
  useEffect(() => {
    setLocalOwner(isOrgMode ? organization?.owner : null);
    setLocalAdmins((isOrgMode ? organization?.admins : league?.admins) || []);
    setLocalStaff((isOrgMode ? organization?.staff : league?.staff) || []);
  }, [organization, league, isOrgMode]);

  // Permissions
  const canManageAdmins = isOrgMode
    ? isOrgOwner || isOrgAdmin || isSuperuser
    : isLeagueAdmin || isSuperuser;
  const canRemoveAdmins = isOrgMode
    ? isOrgOwner || isSuperuser
    : isLeagueAdmin || isSuperuser;
  const canManageStaff = canManageAdmins;
  const canTransferOwnership = isOrgMode && (isOrgOwner || isSuperuser);

  // --- Mutations ---

  const addAdminMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      return isOrgMode ? addOrgAdmin(entityId, userId) : addLeagueAdmin(entityId, userId);
    },
    onSuccess: (user) => {
      toast.success('Admin added');
      setLocalAdmins((prev) => [...prev, user]);
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
      setLocalAdmins((prev) => prev.filter((a) => a.pk !== userId));
      onUpdate?.();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const addStaffMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      return isOrgMode ? addOrgStaff(entityId, userId) : addLeagueStaff(entityId, userId);
    },
    onSuccess: (user) => {
      toast.success('Staff added');
      setLocalStaff((prev) => [...prev, user]);
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
      setLocalStaff((prev) => prev.filter((s) => s.pk !== userId));
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
      if (localOwner) {
        setLocalAdmins((prev) => [...prev, localOwner]);
      }
      setLocalAdmins((prev) => prev.filter((a) => a.pk !== newOwner.pk));
      setLocalOwner(newOwner);
      setShowTransferConfirm(false);
      setTransferTarget(null);
      onUpdate?.();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  // --- AddUserModal handlers ---

  const adminPkSet = useMemo(() => {
    const pks = new Set<number>();
    if (localOwner?.pk) pks.add(localOwner.pk);
    for (const a of localAdmins) {
      if (a.pk) pks.add(a.pk);
    }
    return pks;
  }, [localOwner, localAdmins]);

  const staffPkSet = useMemo(() => {
    const pks = new Set<number>();
    for (const s of localStaff) {
      if (s.pk) pks.add(s.pk);
    }
    return pks;
  }, [localStaff]);

  const handleAddAdmin = useCallback(
    async (payload: AddMemberPayload): Promise<UserType> => {
      if (!payload.user_id) throw new Error('User ID required');
      return addAdminMutation.mutateAsync(payload.user_id);
    },
    [addAdminMutation.mutateAsync]
  );

  const handleAddStaff = useCallback(
    async (payload: AddMemberPayload): Promise<UserType> => {
      if (!payload.user_id) throw new Error('User ID required');
      return addStaffMutation.mutateAsync(payload.user_id);
    },
    [addStaffMutation.mutateAsync]
  );

  const isAdminAdded = useCallback(
    (user: UserType) => user.pk != null && adminPkSet.has(user.pk),
    [adminPkSet]
  );

  const isStaffAdded = useCallback(
    (user: UserType) => user.pk != null && staffPkSet.has(user.pk),
    [staffPkSet]
  );

  const handleTransferClick = (user: UserType) => {
    setTransferTarget(user);
    setShowTransferConfirm(true);
  };

  const confirmTransfer = () => {
    if (transferTarget?.pk) {
      transferOwnershipMutation.mutate(transferTarget.pk);
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
              {localOwner ? (
                <UserRow
                  user={localOwner}
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
              {localAdmins.length > 0 ? (
                localAdmins.map((admin) => (
                  <UserRow
                    key={admin.pk}
                    user={admin}
                    role="admin"
                    canRemove={canRemoveAdmins}
                    canTransfer={canTransferOwnership}
                    onRemove={() => admin.pk && removeAdminMutation.mutate(admin.pk)}
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
              {localStaff.length > 0 ? (
                localStaff.map((member) => (
                  <UserRow
                    key={member.pk}
                    user={member}
                    role="staff"
                    canRemove={canManageStaff}
                    onRemove={() => member.pk && removeStaffMutation.mutate(member.pk)}
                    isRemoving={removeStaffMutation.isPending}
                  />
                ))
              ) : (
                <p className="text-sm text-gray-500 italic">No staff</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Transfer Confirmation Modal */}
      {showTransferConfirm && transferTarget && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Transfer Ownership</h3>
            <p className="py-4">
              Are you sure you want to transfer ownership to{' '}
              <strong>
                {transferTarget.guildNickname ||
                  transferTarget.discordNickname ||
                  transferTarget.username}
              </strong>
              ?
            </p>
            <p className="text-sm text-gray-500">
              You will become an admin after the transfer.
            </p>
            <div className="modal-action">
              <button
                onClick={() => {
                  setShowTransferConfirm(false);
                  setTransferTarget(null);
                }}
                className="btn"
              >
                Cancel
              </button>
              <button
                onClick={confirmTransfer}
                disabled={transferOwnershipMutation.isPending}
                className="btn btn-warning"
              >
                {transferOwnershipMutation.isPending ? (
                  <span className="loading loading-spinner loading-sm" />
                ) : (
                  'Transfer'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Admin Modal */}
      {canManageAdmins && (
        <AddUserModal
          open={showAddAdmin}
          onOpenChange={setShowAddAdmin}
          title={isOrgMode
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
          title={isOrgMode
            ? `Add Staff to ${organization?.name || 'Organization'}`
            : `Add Staff to ${league?.name || 'League'}`
          }
          entityContext={entityContext}
          onAdd={handleAddStaff}
          isAdded={isStaffAdded}
          hasDiscordServer={false}
        />
      )}
    </div>
  );
}
