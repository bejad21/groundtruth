// Localized display labels for ALLOWED_MATERIALS (see backend/app/models.py).
// Fixes a bug where the extracted material_type was humanized to an English
// display string exactly once, at extraction time, and that baked-in English
// string was then shown everywhere — including on the review screen and the
// confirmed receipt — even after switching the whole UI to Arabic. Deriving
// the label from the canonical snake_case value + the current language on
// every render, instead of baking one language in permanently, is the fix.

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

/** snake_case (or arbitrary free text) -> "Title Case" for values with no translation entry. */
function humanize(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Display label for a material_type value in the given language. `value` is
 * always the canonical snake_case value (or arbitrary free text a user typed
 * into the editable field) — never a value that's already been humanized.
 */
export function materialLabel(value: string, lang: 'en' | 'ar'): string {
  if (!value) return '';
  const table = lang === 'ar' ? AR_LABELS : EN_LABELS;
  return table[value] ?? humanize(value);
}

/** Reverse of the EN label (or a passthrough for already-canonical/free-typed text). */
export function toCanonicalMaterial(value: string): string {
  return value.trim().toLowerCase().replaceAll(/\s+/g, '_');
}
