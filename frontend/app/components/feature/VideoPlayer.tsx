import React, { useRef, useState, useEffect } from 'react';
import { cn } from '~/lib/utils';

interface VideoPlayerProps {
  src: string;
  className?: string;
  autoPlay?: boolean;
  loop?: boolean;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({
  src,
  className,
  autoPlay = false,
  loop = true,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [deferredSrc, setDeferredSrc] = useState<string | null>(null);

  // Use requestIdleCallback + IntersectionObserver to defer video loading
  // This prevents blocking the main thread during tab transitions
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    let idleCallbackId: number | undefined;

    // Function to actually set the src during idle time
    const loadVideo = () => {
      if (cancelled) return;

      // Use requestIdleCallback to load during browser idle time
      // Falls back to setTimeout for browsers without support
      const scheduleLoad = window.requestIdleCallback || ((cb) => setTimeout(cb, 50));

      idleCallbackId = scheduleLoad(() => {
        if (!cancelled) {
          setDeferredSrc(src);
        }
      }, { timeout: 200 }) as number; // Max wait 200ms before forcing load
    };

    // Use IntersectionObserver to only load when visible
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          loadVideo();
          observer.disconnect();
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(container);

    return () => {
      cancelled = true;
      observer.disconnect();
      if (idleCallbackId !== undefined) {
        const cancelIdle = window.cancelIdleCallback || clearTimeout;
        cancelIdle(idleCallbackId);
      }
    };
  }, [src]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !deferredSrc) return;

    const handleCanPlay = () => {
      setIsLoading(false);
    };

    const handleError = () => {
      console.error('[VideoPlayer] Error loading video:', deferredSrc);
      setHasError(true);
      setIsLoading(false);
    };

    const handleLoadStart = () => {
      setIsLoading(true);
      setHasError(false);
    };

    video.addEventListener('canplay', handleCanPlay);
    video.addEventListener('error', handleError);
    video.addEventListener('loadstart', handleLoadStart);

    // If video is already ready (cached), update state
    if (video.readyState >= 3) {
      setIsLoading(false);
    }

    return () => {
      video.removeEventListener('canplay', handleCanPlay);
      video.removeEventListener('error', handleError);
      video.removeEventListener('loadstart', handleLoadStart);
    };
  }, [deferredSrc]);

  // Handle autoplay with promise
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !autoPlay || isLoading) return;

    const playPromise = video.play();
    if (playPromise !== undefined) {
      playPromise.catch((error) => {
        // Autoplay was prevented or video was removed - this is fine
        console.log('[VideoPlayer] Autoplay prevented:', error.message);
      });
    }
  }, [autoPlay, isLoading]);

  return (
    <div ref={containerRef} className={cn('relative rounded-lg overflow-hidden', className)}>
      {/* Loading skeleton - uses aspect-video to match typical video dimensions */}
      {isLoading && !hasError && (
        <div className="aspect-video rounded-lg bg-base-300 flex items-center justify-center">
          <div className="w-10 h-10 border-4 border-primary/30 border-t-primary rounded-full animate-spin" />
        </div>
      )}

      {/* Error state */}
      {hasError && (
        <div className="absolute inset-0 bg-base-300 flex items-center justify-center z-10 min-h-[200px]">
          <div className="flex flex-col items-center gap-3">
            <span className="text-sm text-error">Failed to load video</span>
          </div>
        </div>
      )}

      {/* Native video element */}
      <video
        ref={videoRef}
        src={deferredSrc || undefined}
        loop={loop}
        muted
        playsInline
        controls
        preload="metadata"
        className={cn('w-full h-auto', (isLoading || hasError) && 'opacity-0')}
      />
    </div>
  );
};
