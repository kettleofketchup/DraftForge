import { motion } from 'framer-motion';
import { Check, Clock, X } from 'lucide-react';
import { Fragment } from 'react';
import type { ProfileClaimRequest } from '~/components/api/api';
import {
  GAME_LABEL,
  GAME_SLUG,
  GAME_TYPE,
  GAME_TYPES,
  type GameTypeValue,
} from '~/components/game/constants';
import { parseGameMmrs, type GameMmrs } from '~/components/game/gameMmrs';
import { Badge } from '~/components/ui/badge';
import { ConfirmButton, DestructiveButton } from '~/components/ui/buttons';
import { UserAvatar } from '~/components/user/UserAvatar';

type ClaimStatus = 'pending' | 'approved' | 'rejected';

interface ClaimCardProps {
  claim: ProfileClaimRequest;
  index: number;
  onApprove: (claim: ProfileClaimRequest) => void;
  onReject: (claim: ProfileClaimRequest) => void;
}

const getStatusBadge = (status: ClaimStatus) => {
  switch (status) {
    case 'pending':
      return (
        <Badge className="bg-warning text-warning-foreground text-[10px] px-1.5 py-0">
          <Clock className="w-3 h-3 mr-1" />
          Pending
        </Badge>
      );
    case 'approved':
      return (
        <Badge className="bg-success text-success-foreground text-[10px] px-1.5 py-0">
          <Check className="w-3 h-3 mr-1" />
          Approved
        </Badge>
      );
    case 'rejected':
      return (
        <Badge className="bg-error text-error-foreground text-[10px] px-1.5 py-0">
          <X className="w-3 h-3 mr-1" />
          Rejected
        </Badge>
      );
  }
};

const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

function targetMmrs(claim: ProfileClaimRequest): [GameTypeValue, number][] {
  const mmrs: GameMmrs = claim.target_game_mmrs
    ? parseGameMmrs(claim.target_game_mmrs)
    : { [GAME_TYPE.DOTA2]: claim.target_mmr ?? 0 };
  return GAME_TYPES.flatMap((g) => {
    const v = mmrs[g];
    return v ? [[g, v] as [GameTypeValue, number]] : [];
  });
}

export const ClaimCard: React.FC<ClaimCardProps> = ({
  claim,
  index,
  onApprove,
  onReject,
}) => {
  const mmrs = targetMmrs(claim);
  return (
    <motion.div
      key={claim.id}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, delay: Math.min(index * 0.02, 0.2) }}
      className="bg-base-300 hover:bg-base-200 card-3d px-4 py-2 rounded-[1.25rem]
        focus:outline-2 focus:outline-offset-2 focus:outline-primary
        transition-colors"
      data-testid={`claim-card-${claim.id}`}
    >
      <div className="flex flex-col gap-2 p-6">
        <div className="flex items-start gap-4">
          {/* Claimer info */}
          <div className="flex items-center gap-3 flex-1">
            <UserAvatar
              user={{
                pk: claim.claimer,
                username: claim.claimer_username,
                avatar: claim.claimer_avatar,
                discordId: claim.claimer_discord_id,
              }}
              size="lg"
              border="primary"
            />
            <div>
              <div className="font-medium">{claim.claimer_username}</div>
              <div className="text-sm text-muted-foreground">
                wants to claim
              </div>
            </div>
          </div>

          {/* Arrow */}
          <div className="flex items-center text-muted-foreground">
            <span className="text-2xl">&rarr;</span>
          </div>

          {/* Target profile info */}
          {claim.target_user === null ? (
            <div className="flex-1">
              <div className="font-medium" data-testid="claim-target-merged">
                Merged into {claim.claimer_username}
              </div>
            </div>
          ) : (
            <div className="flex-1">
              <div className="font-medium">
                {claim.target_nickname || `Steam ID: ${claim.target_steamid}`}
              </div>
              <div className="text-sm text-muted-foreground">
                {mmrs.length === 0
                  ? 'No MMR'
                  : mmrs.map(([g, v], i) => (
                      <Fragment key={g}>
                        {i > 0 && ' \u00b7 '}
                        <span data-testid={`claim-target-mmr-${GAME_SLUG[g]}`}>
                          {`${GAME_LABEL[g]} ${v} MMR`}
                        </span>
                      </Fragment>
                    ))}
                {claim.target_steamid && (
                  <span className="ml-2">Steam: {claim.target_steamid}</span>
                )}
              </div>
            </div>
          )}

          {/* Status and actions */}
          <div className="flex items-center gap-3">
            {getStatusBadge(claim.status)}

            {claim.status === 'pending' && (
              <div className="flex gap-2">
                <ConfirmButton
                  size="sm"
                  variant="success"
                  onClick={() => onApprove(claim)}
                  data-testid={`approve-claim-btn-${claim.id}`}
                >
                  <Check className="w-4 h-4 mr-1" />
                  Approve
                </ConfirmButton>
                <DestructiveButton
                  size="sm"
                  onClick={() => onReject(claim)}
                  data-testid={`reject-claim-btn-${claim.id}`}
                >
                  <X className="w-4 h-4 mr-1" />
                  Reject
                </DestructiveButton>
              </div>
            )}
          </div>
        </div>

        {/* Additional info */}
        <div className="mt-3 pt-3 border-t border-base-100 text-sm text-muted-foreground flex items-center justify-between flex-wrap gap-2">
          <div>Created: {formatDate(claim.created_at)}</div>
          {claim.reviewed_at && (
            <div>
              Reviewed by {claim.reviewed_by_username} on{' '}
              {formatDate(claim.reviewed_at)}
            </div>
          )}
          {claim.rejection_reason && (
            <div className="text-error">Reason: {claim.rejection_reason}</div>
          )}
        </div>
      </div>
    </motion.div>
  );
};
