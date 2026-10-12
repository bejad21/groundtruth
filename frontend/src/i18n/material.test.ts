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
    expect(new Set(arabicLabels).size).toBe(materials.length);
    for (const label of arabicLabels) {
      expect([...label].some((ch) => ch >= '؀' && ch <= 'ۿ')).toBe(true);
    }
  });

  it('falls back to a humanized version of the raw value for an unrecognized material', () => {
    expect(materialLabel('scrap_metal', 'en')).toBe('Scrap Metal');
    // Values outside the allow-list have no Arabic label and fall back to the humanized text.
    expect(materialLabel('scrap_metal', 'ar')).toBe('Scrap Metal');
  });

  it('is stable for an empty value', () => {
    expect(materialLabel('', 'en')).toBe('');
    expect(materialLabel('', 'ar')).toBe('');
  });
});
