import { usePageNavStore } from '~/store/pageNavStore';
import { MobileNavDropdown } from '~/components/ui/mobile-nav-dropdown';

export function PageNavBar() {
  const options = usePageNavStore((s) => s.options);
  const value = usePageNavStore((s) => s.value);
  const onValueChange = usePageNavStore((s) => s.onValueChange);

  if (!options || options.length === 0 || !onValueChange) return null;

  return (
    <MobileNavDropdown
      options={options}
      value={value}
      onValueChange={onValueChange}
      className="md:hidden mx-2 my-1"
    />
  );
}
