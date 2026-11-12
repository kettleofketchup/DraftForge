import { ChevronNavButton } from '~/components/ui/buttons';

interface PrevRoundButtonProps {
  goToPrevRound: () => void;
  disabled?: boolean;
}
export const PrevRoundButton: React.FC<PrevRoundButtonProps> = ({
  goToPrevRound,
  disabled,
}) => {
  return (
    <ChevronNavButton
      direction="left"
      onClick={goToPrevRound}
      disabled={disabled}
      data-testid="prevRoundButton"
      aria-label="Go to the previous draft round"
    />
  );
};
