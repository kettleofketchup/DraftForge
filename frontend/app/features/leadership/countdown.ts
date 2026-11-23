import { useEffect, useMemo, useReducer } from 'react';

const MINUTE = 60_000;

export function formatCountdown(msLeft: number): string {
  if (!(msLeft > 0)) return 'Closed';
  const minutes = Math.floor(msLeft / MINUTE);
  if (minutes < 1) return '<1m left';
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  if (days > 0) return `${days}d ${hours}h left`;
  if (hours > 0) return `${hours}h ${minutes % 60}m left`;
  return `${minutes}m left`;
}

export function useCountdown(
  iso: string,
  tickMs = 30_000,
): { msLeft: number; closed: boolean } {
  const deadline = useMemo(() => Date.parse(iso), [iso]);
  const [, rerender] = useReducer((n: number) => n + 1, 0);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      const left = deadline - Date.now();
      if (!(left > 0)) return;
      timer = setTimeout(
        () => {
          rerender();
          schedule();
        },
        Math.min(tickMs, left),
      );
    };
    schedule();
    return () => clearTimeout(timer);
  }, [deadline, tickMs]);

  const left = deadline - Date.now();
  const msLeft = left > 0 ? left : 0;
  return { msLeft, closed: msLeft === 0 };
}
