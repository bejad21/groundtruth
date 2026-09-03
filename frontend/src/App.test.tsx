import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import type { ExtractResponse } from './types';

vi.mock('./api/client', () => ({
  checkHealth: vi.fn(async () => true),
  extractTicket: vi.fn(),
  confirmRecord: vi.fn(async () => ({ record_id: 7 })),
}));

import { confirmRecord, extractTicket } from './api/client';

// Mirrors the real response I captured from a live run against ticket_messy.png
// during manual testing (see the audit report) — a smudged-ticket record that
// needs review, exactly the scenario where the Arabic-toggle bug showed up.
const FAKE_RESPONSE: ExtractResponse = {
  record: {
    material_type: 'date_seed_kernels',
    weight_kg: 61500,
    source_name: 'Liwa Palm Cooperative',
    truck_or_driver_id: 'unknown',
    delivery_date: '2026-08-15',
    notes: 'Partial load, second trip pending',
  },
  field_confidences: [
    { field: 'material_type', confidence: 1, reason: '' },
    { field: 'weight_kg', confidence: 1, reason: '' },
    { field: 'source_name', confidence: 1, reason: '' },
    { field: 'truck_or_driver_id', confidence: 1, reason: '' },
    { field: 'delivery_date', confidence: 1, reason: '' },
  ],
  validation_flags: [],
  needs_review: false,
  trace: [{ step: 'result', detail: 'Record accepted automatically.', status: 'ok' }],
  model: 'gemini-lite:gemini-flash-lite-latest',
  run_id: 1,
  confidence_threshold: 0.75,
};

async function runToReviewScreen(user: ReturnType<typeof userEvent.setup>) {
  vi.mocked(extractTicket).mockResolvedValue(FAKE_RESPONSE);
  render(<App />);
  await waitFor(() => screen.getByText('Agent online'));
  const file = new File([new Uint8Array([1, 2, 3])], 'ticket.png', { type: 'image/png' });
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, file);
  await waitFor(() => screen.getByText('Confirm intake record'), { timeout: 5000 });
}

beforeEach(() => {
  vi.mocked(confirmRecord).mockClear();
});

describe('material type localization (the bug: content stayed English in Arabic mode)', () => {
  it('shows an English label for material_type on the review screen by default', async () => {
    const user = userEvent.setup();
    await runToReviewScreen(user);

    expect(screen.getByDisplayValue('Date Seed Kernels')).toBeInTheDocument();
  });

  it('switches the material_type label to Arabic after toggling language', async () => {
    const user = userEvent.setup();
    await runToReviewScreen(user);

    await user.click(screen.getByRole('button', { name: 'ع' }));

    expect(screen.queryByDisplayValue('Date Seed Kernels')).not.toBeInTheDocument();
    const arabicInput = screen.getByDisplayValue(/نوى/);
    expect(arabicInput).toBeInTheDocument();
  });

  it('localizes material_type on the confirmed receipt too, not just the review screen', async () => {
    const user = userEvent.setup();
    await runToReviewScreen(user);

    await user.click(screen.getByRole('button', { name: 'ع' }));
    await user.click(screen.getByText('اعتماد سجل الاستلام'));

    await waitFor(() => screen.getByText('الشحنة جاهزة للاستلام.'));
    expect(screen.getByText(/نوى/)).toBeInTheDocument();
    expect(screen.queryByText('Date Seed Kernels')).not.toBeInTheDocument();
  });

  it('still submits the canonical snake_case material_type to the backend on confirm (no regression)', async () => {
    const user = userEvent.setup();
    await runToReviewScreen(user);

    await user.click(screen.getByText('Confirm intake record'));

    await waitFor(() => expect(confirmRecord).toHaveBeenCalled());
    const submittedRecord = vi.mocked(confirmRecord).mock.calls[0][0];
    expect(submittedRecord.material_type).toBe('date_seed_kernels');
  });

  it('still lets the user free-type a custom material value and submits it unchanged (no regression)', async () => {
    const user = userEvent.setup();
    await runToReviewScreen(user);

    const input = screen.getByDisplayValue('Date Seed Kernels');
    await user.clear(input);
    await user.type(input, 'scrap metal');
    await user.click(screen.getByText('Confirm intake record'));

    await waitFor(() => expect(confirmRecord).toHaveBeenCalled());
    const submittedRecord = vi.mocked(confirmRecord).mock.calls[0][0];
    expect(submittedRecord.material_type).toBe('scrap_metal');
  });
});
