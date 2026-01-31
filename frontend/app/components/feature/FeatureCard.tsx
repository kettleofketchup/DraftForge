import { motion } from 'framer-motion';
import { BookOpen, Film, Image as ImageIcon, Play } from 'lucide-react';
import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Link } from 'react-router';
import { cn } from '~/lib/utils';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '~/components/ui/dialog';
import { Item, ItemContent, ItemMedia, ItemTitle } from '~/components/ui/item';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { VideoPlayer } from './VideoPlayer';

// Video/GIF assets base path (mounted at public/assets/docs in dev, copied during build)
export const ASSETS_BASE = '/assets/docs';

// Global set to track prefetched URLs (prevents duplicate prefetches across components)
const prefetchedUrls = new Set<string>();

// Documentation base URL
export const DOCS_BASE = 'https://kettleofketchup.github.io/DraftForge';

export interface ModalMedia {
  src: string;
  caption: string;
  type?: 'gif' | 'video' | 'image';
}

export interface FeatureCardProps {
  icon: React.ElementType;
  title: string;
  description: string;
  delay?: number;
  comingSoon?: boolean;
  /** Optional GIF source for thumbnail preview */
  gifSrc?: string;
  /** Quick preview media (GIFs) to show in modal Quick Preview tab */
  quickMedia?: ModalMedia[];
  /** Full video media to show in modal Full Video tab */
  modalMedia?: ModalMedia[];
  /** Documentation path (appended to DOCS_BASE) */
  docsPath?: string;
  /** Optional action button for internal navigation */
  action?: {
    label: string;
    href: string;
  };
  /** Color class for icon */
  colorClass?: string;
}

/** Lazy-loading image component using IntersectionObserver + requestIdleCallback */
const LazyImage = ({
  src,
  alt,
  className,
}: {
  src: string;
  alt: string;
  className?: string;
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [deferredSrc, setDeferredSrc] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    let idleCallbackId: number | undefined;

    const loadImage = () => {
      if (cancelled) return;
      const scheduleLoad =
        window.requestIdleCallback || ((cb) => setTimeout(cb, 50));
      idleCallbackId = scheduleLoad(
        () => {
          if (!cancelled) setDeferredSrc(src);
        },
        { timeout: 200 }
      ) as number;
    };

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          loadImage();
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

  return (
    <div ref={containerRef} className={cn('relative min-h-[200px]', className)}>
      {/* Image/GIF skeleton */}
      {isLoading && (
        <div className="absolute inset-0 rounded-lg overflow-hidden bg-base-300 flex items-center justify-center">
          <div className="absolute inset-0 bg-gradient-to-r from-base-300 via-base-200 to-base-300 animate-pulse" />
          {/* Image icon placeholder */}
          <div className="relative flex flex-col items-center gap-2">
            <ImageIcon className="w-12 h-12 text-base-content/20" />
            <div className="w-20 h-2 rounded bg-base-content/10" />
          </div>
        </div>
      )}
      {deferredSrc && (
        <img
          src={deferredSrc}
          alt={alt}
          className={cn('w-full h-auto object-contain rounded-lg', isLoading && 'opacity-0')}
          onLoad={() => setIsLoading(false)}
        />
      )}
    </div>
  );
};

/** Helper component to render a grid of media items */
const MediaGrid = ({ media, title }: { media: ModalMedia[]; title: string }) => (
  <div className={`flex ${media.length > 1 ? 'flex-row gap-4' : 'flex-col'} overflow-auto`}>
    {media.map((item, index) => (
      <div key={index} className={`${media.length > 1 ? 'flex-1 min-w-0' : 'w-full'}`}>
        {item.caption && (
          <div className="text-center mb-2">
            <span className="text-sm font-medium text-base-content/80 bg-base-200 px-3 py-1 rounded-full">
              {item.caption}
            </span>
          </div>
        )}
        {item.type === 'video' ? (
          <VideoPlayer src={item.src} autoPlay loop />
        ) : (
          <LazyImage
            src={item.src}
            alt={item.caption || `${title} preview ${index + 1}`}
          />
        )}
      </div>
    ))}
  </div>
);

export const FeatureCard = ({
  icon: Icon,
  title,
  description,
  delay = 0,
  comingSoon,
  gifSrc,
  quickMedia,
  modalMedia,
  docsPath,
  action,
  colorClass = 'text-primary',
}: FeatureCardProps) => {
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Prefetch videos on hover (uses global Set to prevent duplicates)
  const handlePrefetchVideos = useCallback(() => {
    if (!modalMedia) return;

    modalMedia.forEach((item) => {
      if (item.type === 'video' && !prefetchedUrls.has(item.src)) {
        prefetchedUrls.add(item.src);
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.as = 'video';
        link.href = item.src;
        document.head.appendChild(link);
      }
    });
  }, [modalMedia]);

  const hasPreview = gifSrc || (modalMedia && modalMedia.length > 0) || (quickMedia && quickMedia.length > 0);
  const thumbnailSrc = gifSrc || (quickMedia && quickMedia[0]?.src) || (modalMedia && modalMedia[0]?.src);
  const docsUrl = docsPath ? `${DOCS_BASE}${docsPath}` : undefined;

  // Build quick preview media (GIFs) - use quickMedia if provided, otherwise create from gifSrc
  const quickPreviewMedia: ModalMedia[] = quickMedia || (gifSrc ? [{ src: gifSrc, caption: '', type: 'gif' }] : []);

  // Full video media
  const fullVideoMedia: ModalMedia[] = modalMedia || [];

  // Determine if we have both tabs worth of content
  const hasQuickPreview = quickPreviewMedia.length > 0;
  const hasFullVideo = fullVideoMedia.length > 0;
  const hasBothTabs = hasQuickPreview && hasFullVideo;

  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay }}
        className={`card bg-base-200/50 backdrop-blur border border-primary/10 hover:border-primary/30 transition-all duration-300 hover:shadow-lg hover:shadow-primary/5 relative ${comingSoon ? 'opacity-75' : ''}`}
        onMouseEnter={handlePrefetchVideos}
      >
        {/* Coming Soon Badge - Top Right of Card */}
        {comingSoon && (
          <Badge
            variant="outline"
            className="absolute top-2 right-2 text-[10px] border-warning text-warning bg-base-200 px-1.5 py-0 z-10"
          >
            Coming Soon
          </Badge>
        )}

        {/* Card Header: Icon + Title */}
        <div className="card-header relative z-10">
          <div className="card-header relative z-10">
            <Item
              variant="default"
              size="sm"
              className="!p-0 !flex !flex-row !items-center gap-2"
            >
              <ItemMedia
                variant="icon"
                className="bg-primary/10 border-primary/20 !size-10 shrink-0"
              >
                <Icon className={`w-5 h-5 ${colorClass}`} />
              </ItemMedia>

              <ItemContent className="flex-1">
                <ItemTitle className="w-full text-center text-primary font-semibold text-lg">
                  {title}
                </ItemTitle>
              </ItemContent>
            </Item>
          </div>
        </div>

        {/* Card Body: Description + Preview */}
        <div className="card-body pt-2 relative z-10">
          <p className="text-base-content/70 text-sm">{description}</p>

          {/* GIF Preview - Static thumbnail, click to play in modal */}
          {hasPreview && thumbnailSrc && (
            <div className="mt-3">
              <div
                className="relative overflow-hidden rounded-lg border border-primary/20 cursor-pointer group"
                onClick={() => setIsModalOpen(true)}
              >
                {/* Frozen first frame - CSS pauses animation */}
                <div className="relative">
                  <img
                    src={thumbnailSrc}
                    alt={`${title} preview`}
                    className="w-full h-32 object-cover object-top"
                    style={{ animationPlayState: 'paused' }}
                  />
                  {/* Overlay with play icon */}
                  <div className="absolute inset-0 bg-black/40 flex items-center justify-center group-hover:bg-black/50 transition-colors">
                    <div className="w-12 h-12 rounded-full bg-primary/90 flex items-center justify-center">
                      <Play className="w-6 h-6 text-primary-foreground ml-0.5" fill="currentColor" />
                    </div>
                  </div>
                </div>
                <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
                  <span className="text-xs text-white/80">
                    Click to view
                    {hasBothTabs && ' (GIF & Video)'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Buttons */}
          <div className="mt-3 flex flex-wrap gap-2">
            {/* Learn More - External docs link */}
            {docsUrl && (
              <Button size="sm" variant="outline" asChild>
                <a
                  href={docsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <BookOpen className="w-3 h-3 mr-1" />
                  Learn More
                </a>
              </Button>
            )}

            {/* Action Button - Internal navigation */}
            {action && !comingSoon && (
              <Button size="sm" variant="outline" asChild>
                <Link to={action.href}>{action.label}</Link>
              </Button>
            )}
          </div>
        </div>
      </motion.div>

      {/* Modal for enlarged media - using shadcn Dialog */}
      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent
          className="sm:!max-w-[80vw] !max-w-[80vw] max-h-[70vh] overflow-auto bg-base-300 border-primary/30"
          showCloseButton={true}
          closeButtonVariant="default"
        >
          <DialogHeader>
            <DialogTitle className="text-xl font-semibold text-primary">{title}</DialogTitle>
            <DialogDescription className="sr-only">
              Preview media for {title}
            </DialogDescription>
          </DialogHeader>

          {/* Tabbed content if we have both quick preview and full video */}
          {hasBothTabs ? (
            <Tabs defaultValue="quick">
              <TabsList className="grid w-full grid-cols-2 mb-4">
                <TabsTrigger value="quick" className="flex items-center gap-2">
                  <ImageIcon className="w-4 h-4" />
                  Quick Preview
                </TabsTrigger>
                <TabsTrigger value="full" className="flex items-center gap-2">
                  <Film className="w-4 h-4" />
                  Full Video
                </TabsTrigger>
              </TabsList>

              <TabsContent value="quick" className="mt-0">
                <MediaGrid media={quickPreviewMedia} title={title} />
              </TabsContent>

              <TabsContent value="full" className="mt-0">
                <MediaGrid media={fullVideoMedia} title={title} />
              </TabsContent>
            </Tabs>
          ) : (
            /* Single content area if we only have one type */
            <MediaGrid media={hasQuickPreview ? quickPreviewMedia : fullVideoMedia} title={title} />
          )}

          {/* Learn More */}
          {docsUrl && (
            <div className="pt-2">
              <a
                href={docsUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm text-primary hover:text-primary/80 transition-colors"
              >
                <BookOpen className="w-4 h-4" />
                View documentation
              </a>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};
