/**
 * Admin Team management section for organizations and leagues.
 * Provides UI for managing owner, admins, and staff.
 * Uses local state to avoid full page re-renders on updates.
 */

import { useState, useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Crown, Shield, User, X } from 'lucide-react';
import { toast } from 'sonner';
import type { UserType } from '~/components/user/types';
import type { OrganizationType } from '~/components/organization/schemas';
import type { LeagueType } from '~/components/league/schemas';
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
import { UserSearchInput } from './UserSearchInput';

interface AdminTeamSectionProps {
  // For organization management
  organization?: OrganizationType | null;
  // For league management
  league?: LeagueType | null;
  // Callback when team is updated
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
    <div className="flex items-center justify-between py-2 px-3 bg-base-200 rounded-lg">
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

  const isSuperuser = useIsSuperuser();
  const isOrgOwner = useIsOrganizationOwner(organization);
  const isOrgAdmin = useIsOrganizationAdmin(organization);
  const isLeagueAdmin = useIsLeagueAdmin(league, organization ? [organization] : undefined);

  const isOrgMode = !!organization && !league;
  const entityId = isOrgMode ? organization?.pk : league?.pk;

  // Local state for team members - avoids full page re-render on updates
  const [localOwner, setLocalOwner] = useState<UserType | null | undefined>(
    isOrgMode ? organization?.owner : null
  );
  const [localAdmins, setLocalAdmins] = useState<UserType[]>(
    (isOrgMode ? organization?.admins : league?.admins) || []
  );
  const [localStaff, setLocalStaff] = useState<UserType[]>(
    (isOrgMode ? organization?.staff : league?.staff) || []
  );

  // Sync local state when props change (e.g., modal reopens with new data)
  useEffect(() => {
    setLocalOwner(isOrgMode ? organization?.owner : null);
    setLocalAdmins((isOrgMode ? organization?.admins : league?.admins) || []);
    setLocalStaff((isOrgMode ? organization?.staff : league?.staff) || []);
  }, [organization, league, isOrgMode]);

  // Determine permissions
  const canManageAdmins = isOrgMode
    ? isOrgOwner || isOrgAdmin || isSuperuser
    : isLeagueAdmin || isSuperuser;
  const canRemoveAdmins = isOrgMode
    ? isOrgOwner || isSuperuser
    : isLeagueAdmin || isSuperuser;
  const canManageStaff = canManageAdmins;
  const canTransferOwnership = isOrgMode && (isOrgOwner || isSuperuser);

  // Add admin mutation
  const addAdminMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      if (isOrgMode) {
        return addOrgAdmin(entityId, userId);
      } else {
        return addLeagueAdmin(entityId, userId);
      }
    },
    onSuccess: (user) => {
      toast.success('Admin added');
      setLocalAdmins((prev) => [...prev, user]);
      onUpdate?.();
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  // Remove admin mutation
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
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  // Add staff mutation
  const addStaffMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      if (isOrgMode) {
        return addOrgStaff(entityId, userId);
      } else {
        return addLeagueStaff(entityId, userId);
      }
    },
    onSuccess: (user) => {
      toast.success('Staff added');
      setLocalStaff((prev) => [...prev, user]);
      onUpdate?.();
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  // Remove staff mutation
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
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  // Transfer ownership mutation
  const transferOwnershipMutation = useMutation({
    mutationFn: async (userId: number) => {
      if (!entityId) throw new Error('No entity ID');
      return transferOrgOwnership(entityId, userId);
    },
    onSuccess: (newOwner) => {
      toast.success('Ownership transferred');
      // Old owner becomes admin
      if (localOwner) {
        setLocalAdmins((prev) => [...prev, localOwner]);
      }
      // New owner is removed from admins
      setLocalAdmins((prev) => prev.filter((a) => a.pk !== newOwner.pk));
      // Set new owner
      setLocalOwner(newOwner);
      setShowTransferConfirm(false);
      setTransferTarget(null);
      onUpdate?.();
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const handleTransferClick = (user: UserType) => {
    setTransferTarget(user);
    setShowTransferConfirm(true);
  };

  const confirmTransfer = () => {
    if (transferTarget?.pk) {
      transferOwnershipMutation.mutate(transferTarget.pk);
    }
  };

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

          {/* Inherited Organizations Note (League only) */}
          {!isOrgMode && league?.organizations && league.organizations.length > 0 && (
            <div className="text-sm text-gray-500 bg-base-200 p-3 rounded-lg">
              <p className="font-medium mb-1">Inherited permissions from:</p>
              <ul className="list-disc list-inside">
                {league.organizations.map((org) => (
                  <li key={org.pk}>{org.name}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Admins Section */}
          <div>
            <h4 className="font-medium mb-2 flex items-center gap-2">
              <Shield className="h-4 w-4 text-blue-500" />
              Admins
            </h4>
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
            {canManageAdmins && (
              <div className="mt-3">
                <UserSearchInput
                  onSelect={(user) => user.pk && addAdminMutation.mutate(user.pk)}
                  placeholder="Search to add admin..."
                  isLoading={addAdminMutation.isPending}
                  excludeIds={[
                    ...localAdmins.map((a) => a.pk).filter(Boolean) as number[],
                    localOwner?.pk,
                  ].filter(Boolean) as number[]}
                />
              </div>
            )}
          </div>

          {/* Staff Section */}
          <div>
            <h4 className="font-medium mb-2 flex items-center gap-2">
              <User className="h-4 w-4 text-gray-500" />
              Staff
            </h4>
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
            {canManageStaff && (
              <div className="mt-3">
                <UserSearchInput
                  onSelect={(user) => user.pk && addStaffMutation.mutate(user.pk)}
                  placeholder="Search to add staff..."
                  isLoading={addStaffMutation.isPending}
                  excludeIds={localStaff.map((s) => s.pk).filter(Boolean) as number[]}
                />
              </div>
            )}
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
    </div>
  );
}
