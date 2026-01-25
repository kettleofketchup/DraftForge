import { ChevronNavButton } from '~/components/ui/buttons';

interface PrevRoundButtonProps {
  goToPrevRound: () => void;
}
export const PrevRoundButton: React.FC<PrevRoundButtonProps> = ({
  goToPrevRound,
}) => {
  return (
    <ChevronNavButton
      direction="left"
      onClick={goToPrevRound}
      aria-label="Go to the previous draft round"
    />
  );
};
