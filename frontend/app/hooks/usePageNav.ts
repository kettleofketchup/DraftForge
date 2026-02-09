import { useEffect } from 'react';
import {
  usePageNavStore,
  type PageNavOption,
} from '~/store/pageNavStore';

export function usePageNav(
  options: PageNavOption[] | null,
  value: string,
  onValueChange: (v: string) => void,
): void {
  const setPageNav = usePageNavStore((s) => s.setPageNav);
  const clearPageNav = usePageNavStore((s) => s.clearPageNav);
  const updateValue = usePageNavStore((s) => s.updateValue);

  // Register/update page nav when options or value change
  useEffect(() => {
    if (options) {
      setPageNav(options, value, onValueChange);
    }
  }, [options, value, onValueChange, setPageNav]);

  // Clear on unmount
  useEffect(() => {
    return () => clearPageNav();
  }, [clearPageNav]);
}
