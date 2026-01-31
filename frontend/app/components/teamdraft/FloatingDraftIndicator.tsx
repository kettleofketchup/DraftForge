import { motion } from 'framer-motion';
import { ClipboardPen } from 'lucide-react';
import { Link } from 'react-router';
import { useUserStore } from '~/store/userStore';
import { getDraftUrl } from './utils';

const MotionLink = motion.create(Link);

/**
 * Floating indicator shown at bottom-right of screen when user has active drafts.
 * For mobile usage - provides a prominent, always-visible notification.
 * Hidden on desktop (md breakpoint and above) where ActiveDraftBanner is shown instead.
 */
export const FloatingDraftIndicator: React.FC = () => {
  const activeDrafts = useUserStore(
    (state) => state.currentUser?.active_drafts,
  );

  if (!activeDrafts || activeDrafts.length === 0) {
    return null;
  }

  // Show first draft for mobile floating indicator
  const firstDraft = activeDrafts[0];
  const draftLabel =
    firstDraft.type === 'team_draft' ? 'Team Draft' : 'Hero Draft';

  return (
    <MotionLink
      data-testid="floating-draft-indicator"
      to={getDraftUrl(firstDraft)}
      className="fixed bottom-6 right-6 z-50 bg-red-600 hover:bg-red-700
                 text-white px-4 py-3 rounded-full shadow-lg
                 flex items-center gap-2 cursor-pointer
                 transition-colors duration-200 md:hidden"
      animate={{
        scale: [1, 1.05, 1],
      }}
      transition={{
        duration: 1.5,
        repeat: Infinity,
        ease: 'easeInOut',
      }}
      aria-label={`Active ${draftLabel}`}
      role="alert"
    >
      <ClipboardPen className="w-5 h-5" />
      <span className="font-medium">
        {activeDrafts.length > 1
          ? `${activeDrafts.length} Active Drafts`
          : `Active ${draftLabel}`}
      </span>
    </MotionLink>
  );
};
