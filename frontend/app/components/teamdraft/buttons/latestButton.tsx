import { NavButton } from '~/components/ui/buttons';

interface LatestRoundButtonProps {
  goToLatestRound: () => void;
  disabled?: boolean;
}
export const LatestRoundButton: React.FC<LatestRoundButtonProps> = ({
  goToLatestRound,
  disabled,
}) => {
  return (
    <NavButton
      onClick={goToLatestRound}
      disabled={disabled}
      aria-label="Go to the latest draft round"
    >
      Latest
    </NavButton>
  );
};
