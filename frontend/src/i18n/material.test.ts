import { describe, expect, it } from 'vitest';
import { materialLabel } from './material';

describe('materialLabel', () => {
  it('returns the English title-case label for a known material', () => {
    expect(materialLabel('date_seed_kernels', 'en')).toBe('Date Seed Kernels');
  });

  it('returns a genuinely different, real Arabic string for the same material', () => {
    const en = materialLabel('date_seed_kernels', 'en');
    const ar = materialLabel('date_seed_kernels', 'ar');
    expect(ar).not.toBe(en);
    expect([...ar].some((ch) => ch >= '؀' && ch <= 'ۿ')).toBe(true);
  });

  it('translates every allowed material to a distinct Arabic label', () => {
    const materials = [
      'date_palm_fronds',
      'date_palm_biomass',
      'date_seed_kernels',
      'mixed_agricultural_residue',
      'other_organic_waste',
    ];
    const arabicLabels = materials.map((m) => materialLabel(m, 'ar'));
    expect(new Set(arabicLabels).size).toBe(materials.length); // no duplicates/fallback collisions
    for (const label of arabicLabels) {
      expect([...label].some((ch) => ch >= '؀' && ch <= 'ۿ')).toBe(true);
    }
  });

  it('falls back to a humanized version of the raw value for an unrecognized material', () => {
    expect(materialLabel('scrap_metal', 'en')).toBe('Scrap Metal');
    // No Arabic translation exists for a value outside the allow-list — falling back to
    // the humanized value (rather than throwing, or silently showing raw snake_case) is
    // the correct behavior for free-text edits.
    expect(materialLabel('scrap_metal', 'ar')).toBe('Scrap Metal');
  });

  it('is stable for an empty value', () => {
    expect(materialLabel('', 'en')).toBe('');
    expect(materialLabel('', 'ar')).toBe('');
  });
});
