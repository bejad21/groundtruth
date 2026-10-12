// Localized display labels for ALLOWED_MATERIALS (see backend/app/models.py).
// State holds the canonical snake_case value; labels are derived per render so
// they follow the current language.

const EN_LABELS: Record<string, string> = {
  date_palm_fronds: 'Date Palm Fronds',
  date_palm_biomass: 'Date Palm Biomass',
  date_seed_kernels: 'Date Seed Kernels',
  mixed_agricultural_residue: 'Mixed Agricultural Residue',
  other_organic_waste: 'Other Organic Waste',
};

const AR_LABELS: Record<string, string> = {
  date_palm_fronds: 'سعف نخيل التمر',
  date_palm_biomass: 'الكتلة الحيوية لنخيل التمر',
  date_seed_kernels: 'نوى بذور التمر',
  mixed_agricultural_residue: 'مخلفات زراعية مختلطة',
  other_organic_waste: 'نفايات عضوية أخرى',
};

/** Title Case fallback for values with no translation entry. */
function humanize(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Display label for a canonical snake_case value, or free text typed into the editable field. */
export function materialLabel(value: string, lang: 'en' | 'ar'): string {
  if (!value) return '';
  const table = lang === 'ar' ? AR_LABELS : EN_LABELS;
  return table[value] ?? humanize(value);
}

/** Normalize a label or free text to snake_case. */
export function toCanonicalMaterial(value: string): string {
  return value.trim().toLowerCase().replaceAll(/\s+/g, '_');
}
