import { useEffect, useRef, useState } from 'react';

export interface AnimationFrameClockOptions<T> {
  derive: () => T;
  isFrozen: boolean;
  inputs: readonly unknown[];
}

export function useAnimationFrameClock<T>({ derive, isFrozen, inputs }: AnimationFrameClockOptions<T>): T {
  const [value, setValue] = useState<T>(() => derive());
  const deriveRef = useRef(derive);
  const frozenRef = useRef(isFrozen);
  deriveRef.current = derive;
  frozenRef.current = isFrozen;

  // Re-derive on input change even while frozen.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setValue(deriveRef.current()), inputs);

  useEffect(() => {
    let rafId = 0;
    const frame = () => {
      if (!frozenRef.current) setValue(deriveRef.current());
      rafId = requestAnimationFrame(frame);
    };
    rafId = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(rafId);
  }, []);

  return value;
}
