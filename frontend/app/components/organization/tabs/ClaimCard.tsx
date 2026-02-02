import { motion } from 'framer-motion';
import { Check, Clock, X } from 'lucide-react';
import type { ProfileClaimRequest } from '~/components/api/api';
import { Avatar, AvatarFallback, AvatarImage } from '~/components/ui/avatar';
import { Badge } from '~/components/ui/badge';
import { ConfirmButton, DestructiveButton } from '~/components/ui/buttons';

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
        <Badge className="bg-yellow-600 text-white text-[10px] px-1.5 py-0">
          <Clock className="w-3 h-3 mr-1" />
          Pending
        </Badge>
      );
    case 'approved':
      return (
        <Badge className="bg-green-600 text-white text-[10px] px-1.5 py-0">
          <Check className="w-3 h-3 mr-1" />
          Approved
        </Badge>
      );
    case 'rejected':
      return (
        <Badge className="bg-red-600 text-white text-[10px] px-1.5 py-0">
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

export const ClaimCard: React.FC<ClaimCardProps> = ({
  claim,
  index,
  onApprove,
  onReject,
}) => {
  return (
    <motion.div
      key={claim.id}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, delay: Math.min(index * 0.02, 0.2) }}
      className="card card-compact bg-base-300 rounded-2xl hover:bg-base-200
        focus:outline-2 focus:outline-offset-2 focus:outline-primary
        transition-colors"
      data-testid={`claim-card-${claim.id}`}
    >
      <div className="card-body">
        <div className="flex items-start gap-4">
          {/* Claimer info */}
          <div className="flex items-center gap-3 flex-1">
            <Avatar className="h-10 w-10 ring-2 ring-primary">
              {claim.claimer_avatar && (
                <AvatarImage src={claim.claimer_avatar} alt={claim.claimer_username} />
              )}
              <AvatarFallback>
                {claim.claimer_username.charAt(0).toUpperCase()}
              </AvatarFallback>
            </Avatar>
            <div>
              <div className="font-medium">{claim.claimer_username}</div>
              <div className="text-sm text-muted-foreground">wants to claim</div>
            </div>
          </div>

          {/* Arrow */}
          <div className="flex items-center text-muted-foreground">
            <span className="text-2xl">&rarr;</span>
          </div>

          {/* Target profile info */}
          <div className="flex-1">
            <div className="font-medium">
              {claim.target_nickname || `Steam ID: ${claim.target_steamid}`}
            </div>
            <div className="text-sm text-muted-foreground">
              {claim.target_mmr ? `${claim.target_mmr} MMR` : 'No MMR'}
              {claim.target_steamid && (
                <span className="ml-2">Steam: {claim.target_steamid}</span>
              )}
            </div>
          </div>

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
              Reviewed by {claim.reviewed_by_username} on {formatDate(claim.reviewed_at)}
            </div>
          )}
          {claim.rejection_reason && (
            <div className="text-red-500">Reason: {claim.rejection_reason}</div>
          )}
        </div>
      </div>
    </motion.div>
  );
};
