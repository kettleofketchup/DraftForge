import { ChevronNavButton } from '~/components/ui/buttons';

interface NextRoundButtonProps {
  goToNextRound: () => void;
  disabled?: boolean;
}
export const NextRoundButton: React.FC<NextRoundButtonProps> = ({
  goToNextRound,
  disabled,
}) => {
  return (
    <ChevronNavButton
      direction="right"
      onClick={goToNextRound}
      disabled={disabled}
      aria-label="Go to the next draft round"
    />
  );
};
