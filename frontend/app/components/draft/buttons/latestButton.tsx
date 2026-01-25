import { NavButton } from '~/components/ui/buttons';

interface LatestRoundButtonProps {
  goToLatestRound: () => void;
}
export const LatestRoundButton: React.FC<LatestRoundButtonProps> = ({
  goToLatestRound,
}) => {
  return (
    <NavButton
      direction="latest"
      onClick={goToLatestRound}
      aria-label="Go to the latest draft round"
    />
  );
};
