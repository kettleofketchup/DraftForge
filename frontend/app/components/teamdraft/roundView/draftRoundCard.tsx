import { motion } from 'framer-motion';
import { memo } from 'react';
import { Badge } from '~/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '~/components/ui/card';
import type { DraftRoundType } from '~/index';
import { DisplayName } from '~/index';
import { UserAvatar } from '~/components/user/UserAvatar';

// Stable animation objects to prevent re-renders
const inViewAnimation = {
  opacity: 1,
  transition: { delay: 0.05, duration: 0.5 },
};
const hoverAnimation = { scale: 1.1 };
const focusAnimation = { scale: 1.05 };

interface DraftRoundCardProps {
  draftRound: DraftRoundType;
  maxRounds: number;
  isCur: boolean;
}

// Custom comparison for memo - check key properties that affect display
const draftRoundCardPropsAreEqual = (
  prevProps: DraftRoundCardProps,
  nextProps: DraftRoundCardProps
): boolean => {
  if (prevProps.isCur !== nextProps.isCur) return false;
  if (prevProps.maxRounds !== nextProps.maxRounds) return false;
  if (prevProps.draftRound?.pk !== nextProps.draftRound?.pk) return false;
  if (prevProps.draftRound?.pick_number !== nextProps.draftRound?.pick_number) return false;
  if (prevProps.draftRound?.captain?.pk !== nextProps.draftRound?.captain?.pk) return false;
  if (prevProps.draftRound?.choice?.pk !== nextProps.draftRound?.choice?.pk) return false;
  // Also check team members count for team display
  if (prevProps.draftRound?.team?.members?.length !== nextProps.draftRound?.team?.members?.length) return false;
  return true;
};

export const DraftRoundCard = memo(
  ({ draftRound, maxRounds, isCur }: DraftRoundCardProps) => {
    const bgColor = isCur ? 'bg-green-900' : 'bg-gray-800';

    return (
      <motion.div
        whileInView={inViewAnimation}
        whileHover={hoverAnimation}
        whileFocus={focusAnimation}
        className="flex items-center justify-center w-full"
      >
        <Card className={`w-full p-2  ${bgColor} py-4`}>
          <CardHeader>
            <CardTitle className="flex justify-center">
              {isCur ? 'Current Captain: ' : 'Next Captain: '}
              {draftRound?.captain ? DisplayName(draftRound.captain) : 'No captain selected'}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <CardDescription>
              <div
                className="flex items-center justify-between justify-center
            align-middle"
              >
                <UserAvatar user={draftRound?.captain ?? undefined} size="xl" />
              </div>
            </CardDescription>
          </CardContent>
          <CardFooter className="flex justify-between items-center justify-center">
            <Badge>
              Round {draftRound?.pick_number ?? 0}/{maxRounds}
            </Badge>
          </CardFooter>
        </Card>
      </motion.div>
    );
  },
  draftRoundCardPropsAreEqual
);
