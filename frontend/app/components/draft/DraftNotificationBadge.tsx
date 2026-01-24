import { motion } from 'framer-motion';
import { useUserStore } from '~/store/userStore';

/**
 * Flashing notification badge shown when user has active drafts.
 *
 * Displays as a small red dot that pulses/flashes to draw attention.
 * Should be positioned absolutely within a relative parent (e.g., user avatar).
 */
export const DraftNotificationBadge: React.FC = () => {
  const activeDrafts = useUserStore(
    (state) => state.currentUser?.active_drafts,
  );

  if (!activeDrafts || activeDrafts.length === 0) {
    return null;
  }

  return (
    <motion.div
      data-testid="draft-notification-badge"
      className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full border-2 border-white shadow-md"
      animate={{
        scale: [1, 1.2, 1],
        opacity: [1, 0.7, 1],
      }}
      transition={{
        duration: 1,
        repeat: Infinity,
        ease: 'easeInOut',
      }}
      aria-label="You have active drafts"
      role="status"
    />
  );
};
