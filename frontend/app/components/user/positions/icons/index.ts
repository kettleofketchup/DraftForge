import { getLogger } from '~/lib/logger';

const log = getLogger('positionIcons');

// Import SVGs as React components using ?react suffix
import { CarrySVG } from './carry';
import { HardSupportSVG } from './hardSupportIcon';
import { MidSVG } from './mid';
import { OfflaneSVG } from './offlane';
import { SoftSupportSVG } from './softSupport';

export { CarrySVG, HardSupportSVG, MidSVG, OfflaneSVG, SoftSupportSVG };
