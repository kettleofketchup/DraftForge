import { useContext } from 'react';

import { DisplayOrgContext } from '~/lib/displayOrgContext';

export function useDisplayOrgId(): number | null {
  return useContext(DisplayOrgContext);
}
