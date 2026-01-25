import { ChevronNavButton } from '~/components/ui/buttons';

interface NextRoundButtonProps {
  goToNextRound: () => void;
}
export const NextRoundButton: React.FC<NextRoundButtonProps> = ({
  goToNextRound,
}) => {
  return (
    <ChevronNavButton
      direction="right"
      onClick={goToNextRound}
      aria-label="Go to the next draft round"
    />
  );
};
