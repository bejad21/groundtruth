import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

// jsdom doesn't implement the Blob URL APIs the app uses for document previews.
if (!URL.createObjectURL) {
  URL.createObjectURL = vi.fn(() => 'blob:mock-preview-url');
}
if (!URL.revokeObjectURL) {
  URL.revokeObjectURL = vi.fn();
}
