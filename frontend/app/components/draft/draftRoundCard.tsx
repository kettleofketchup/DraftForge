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
import { AvatarUrl } from '~/index';
export const DraftRoundCard = memo(
  ({
    draftRound,
    maxRounds,
    isCur,
  }: {
    draftRound: DraftRoundType;
    maxRounds: number;
    isCur: boolean;
  }) => {
    const bgColor = isCur ? 'bg-green-900' : 'bg-gray-800';
    return (
      <Card className={`w-full max-w-lg ${bgColor} py-4`}>
        <CardHeader>
          <CardTitle className="flex justify-center">
            {isCur ? 'Current Captain: ' : 'Next Captain: '}
            {draftRound?.captain?.nickname ||
              draftRound?.captain?.username ||
              'No captain selected'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <CardDescription>
            <div
              className="flex items-center justify-between justify-center
            align-middle"
            >
              <img
                src={AvatarUrl(draftRound?.captain)}
                alt="User Avatar"
                className="w-12 h-12 rounded-full"
              />{' '}
            </div>
          </CardDescription>
        </CardContent>
        <CardFooter className="flex justify-between items-center justify-center">
          <Badge>
            Round {draftRound?.pick_number ?? 0}/{maxRounds}
          </Badge>
        </CardFooter>
      </Card>
    );
  },
);
