import { motion, AnimatePresence } from 'framer-motion';
import { BookOpen, Film, Image as ImageIcon, Play, X } from 'lucide-react';
import React, { useState } from 'react';
import { Link } from 'react-router';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { Item, ItemContent, ItemMedia, ItemTitle } from '~/components/ui/item';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { VideoPlayer } from './VideoPlayer';

// Video/GIF assets base path (mounted at public/assets/docs in dev, copied during build)
export const ASSETS_BASE = '/assets/docs';

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
          <img
            src={item.src}
            alt={item.caption || `${title} preview ${index + 1}`}
            className="w-full h-auto object-contain rounded-lg"
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

      {/* Modal for enlarged media */}
      <AnimatePresence>
        {isModalOpen && (hasQuickPreview || hasFullVideo) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
            onClick={() => setIsModalOpen(false)}
          >
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              className="relative w-[95vw] max-w-7xl max-h-[90vh] overflow-hidden rounded-xl border border-primary/30 shadow-2xl bg-base-300"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Close button */}
              <button
                onClick={() => setIsModalOpen(false)}
                className="absolute top-2 right-2 z-10 p-1.5 rounded-full bg-base-200/90 hover:bg-base-300 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>

              {/* Title */}
              <div className="p-4 pb-2">
                <h3 className="text-xl font-semibold text-primary">{title}</h3>
              </div>

              {/* Tabbed content if we have both quick preview and full video */}
              {hasBothTabs ? (
                <Tabs defaultValue="quick" className="px-4 pb-4">
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
                <div className="px-4 pb-4">
                  <MediaGrid media={hasQuickPreview ? quickPreviewMedia : fullVideoMedia} title={title} />
                </div>
              )}

              {/* Learn More */}
              {docsUrl && (
                <div className="px-4 pb-4">
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
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};
