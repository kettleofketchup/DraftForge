import { cn } from '~/lib/utils';
import { memo, useState, useCallback } from 'react';

interface SimpleAvatarProps {
  src?: string;
  alt: string;
  fallback: string;
  className?: string;
  fallbackClassName?: string;
  onError?: () => void;
}

/**
 * High-performance avatar using CSS for fallback display.
 * No context, no loading state tracking - just img with CSS object-fit.
 * Reduces re-renders compared to Radix Avatar which uses internal state.
 *
 * Fallback is always rendered but hidden via opacity when image loads.
 * This avoids the 3x render cascade from Radix's idle->loading->loaded state.
 */
export const SimpleAvatar = memo(function SimpleAvatar({
  src,
  alt,
  fallback,
  className,
  fallbackClassName,
  onError,
}: SimpleAvatarProps) {
  const [hasError, setHasError] = useState(false);

  const handleError = useCallback(() => {
    setHasError(true);
    onError?.();
  }, [onError]);

  const showImage = src && !hasError;

  return (
    <div
      className={cn(
        'relative flex shrink-0 overflow-hidden rounded-full bg-muted',
        className
      )}
    >
      {/* Image - browser handles loading natively */}
      {showImage && (
        <img
          src={src}
          alt={alt}
          onError={handleError}
          className="aspect-square h-full w-full object-cover"
          loading="lazy"
          decoding="async"
        />
      )}

      {/* Fallback - shown when no src or error */}
      <span
        className={cn(
          'absolute inset-0 flex items-center justify-center rounded-full bg-muted',
          showImage ? 'opacity-0' : 'opacity-100',
          fallbackClassName
        )}
        aria-hidden={showImage}
      >
        {fallback}
      </span>
    </div>
  );
});

export default SimpleAvatar;
