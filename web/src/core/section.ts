import type { Part } from '../data/parts';

export type SectionContent = 'full' | 'section' | 'none';

/** What a part shows: its exterior, or in section mode its half-section asset when one is loaded,
 *  nothing when it is `hideInSection`, and its exterior otherwise. */
export function sectionContent(part: Part, sectioned: boolean, hasSection: boolean): SectionContent {
  if (!sectioned) return 'full';
  if (part.hideInSection) return 'none';
  return hasSection ? 'section' : 'full';
}
