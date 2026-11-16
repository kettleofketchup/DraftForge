import { useEffect } from 'react';
import { useLocation, useNavigate, type NavigateFunction } from 'react-router';

export const probeNavigate: { current: NavigateFunction | null } = {
  current: null,
};

export function LocationProbe(): React.JSX.Element {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    probeNavigate.current = navigate;
    return () => {
      probeNavigate.current = null;
    };
  }, [navigate]);
  return <span data-testid="location">{pathname}</span>;
}
