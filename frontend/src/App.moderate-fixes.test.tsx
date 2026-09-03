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

const CLEAN_RESPONSE: ExtractResponse = {
  record: {
    material_type: 'date_palm_fronds',
    weight_kg: 8420,
    source_name: 'Al Ain Date Farms Co.',
    truck_or_driver_id: 'DXB-44215',
    delivery_date: '2026-08-12',
    notes: '',
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
  model: 'gemini:gemini-flash-latest',
  run_id: 1,
  confidence_threshold: 0.75,
};

async function runToReviewScreen(user: ReturnType<typeof userEvent.setup>, response: ExtractResponse) {
  vi.mocked(extractTicket).mockResolvedValue(response);
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

describe('rules-passed counter accuracy', () => {
  it('shows 4/4 for a fully clean record', async () => {
    const user = userEvent.setup();
    await runToReviewScreen(user, CLEAN_RESPONSE);

    expect(screen.getByText('4 / 4 rules passed')).toBeInTheDocument();
  });

  it('counts two flags in the same rule category as one failure, not two', async () => {
    // Same shape a hand-edited record could produce: two separate weight
    // complaints. The old counter (RULE_KEYS.length - validation_flags.length)
    // would double-subtract these and wrongly report 2/4.
    const response: ExtractResponse = {
      ...CLEAN_RESPONSE,
      validation_flags: [
        { field: 'weight_kg', severity: 'warning', message: 'Weight looks unusually high.', rule: 'weight' },
        { field: 'weight_kg', severity: 'warning', message: 'Double-check the reading.', rule: 'weight' },
      ],
      needs_review: true,
    };
    const user = userEvent.setup();
    await runToReviewScreen(user, response);

    expect(screen.getByText('3 / 4 rules passed')).toBeInTheDocument();
  });

  it('counts a low-confidence field as a failed rule, not just flagged fields (the old counter ignored confidence entirely)', async () => {
    const response: ExtractResponse = {
      ...CLEAN_RESPONSE,
      field_confidences: CLEAN_RESPONSE.field_confidences.map((f) =>
        f.field === 'source_name' ? { ...f, confidence: 0.4 } : f
      ),
      needs_review: true,
    };
    const user = userEvent.setup();
    await runToReviewScreen(user, response);

    expect(screen.getByText('3 / 4 rules passed')).toBeInTheDocument();
  });
});

describe('weight field rejects non-numeric input', () => {
  it('shows an inline error and disables Confirm when the weight field holds non-numeric text', async () => {
    const user = userEvent.setup();
    await runToReviewScreen(user, CLEAN_RESPONSE);

    const weightInput = screen.getByDisplayValue('8420');
    await user.clear(weightInput);
    await user.type(weightInput, 'not a number');

    expect(screen.getByText(/Enter a valid number./)).toBeInTheDocument();
    expect(screen.getByText('Confirm intake record').closest('button')).toBeDisabled();
  });

  it('clears the error and re-enables Confirm once a valid number is entered, and submits the correct value', async () => {
    const user = userEvent.setup();
    await runToReviewScreen(user, CLEAN_RESPONSE);

    const weightInput = screen.getByDisplayValue('8420');
    await user.clear(weightInput);
    await user.type(weightInput, 'garbage');
    expect(screen.getByText('Confirm intake record').closest('button')).toBeDisabled();

    await user.clear(weightInput);
    await user.type(weightInput, '9500');
    expect(screen.queryByText(/Enter a valid number./)).not.toBeInTheDocument();

    await user.click(screen.getByText('Confirm intake record'));
    await waitFor(() => expect(confirmRecord).toHaveBeenCalled());
    const submittedRecord = vi.mocked(confirmRecord).mock.calls[0][0];
    expect(submittedRecord.weight_kg).toBe(9500);
  });

  it('never lets invalid weight text reach confirmRecord even if the button is force-clicked twice quickly (no regression on the disabled guard)', async () => {
    const user = userEvent.setup();
    await runToReviewScreen(user, CLEAN_RESPONSE);

    const weightInput = screen.getByDisplayValue('8420');
    await user.clear(weightInput);
    await user.type(weightInput, 'abc');
    const confirmButton = screen.getByText('Confirm intake record').closest('button')!;
    await user.click(confirmButton);
    await user.click(confirmButton);

    expect(confirmRecord).not.toHaveBeenCalled();
  });
});

describe('confidence threshold comes from the backend response, not a hardcoded 0.75', () => {
  it('flags a field as low-confidence using the response threshold, not a fixed 0.75', async () => {
    // 0.8 confidence would NOT be flagged under a hardcoded 0.75 threshold,
    // but the backend says its real threshold for this run was 0.9 — so it
    // must be flagged. This is the case that tells the two implementations apart.
    const response: ExtractResponse = {
      ...CLEAN_RESPONSE,
      confidence_threshold: 0.9,
      field_confidences: CLEAN_RESPONSE.field_confidences.map((f) =>
        f.field === 'source_name' ? { ...f, confidence: 0.8 } : f
      ),
      needs_review: true,
    };
    const user = userEvent.setup();
    await runToReviewScreen(user, response);

    expect(screen.getByText('80% confidence')).toBeInTheDocument();
    // The rules-passed counter must agree: the confidence category failed too.
    expect(screen.getByText('3 / 4 rules passed')).toBeInTheDocument();
  });

  it('does not flag the same 0.8-confidence field when the response threshold is lower', async () => {
    // Same field, same confidence, but this run's real threshold (0.6) means
    // 0.8 clears it — proving the frontend reacts to the response value both
    // ways, not just hardcoding a different fixed number.
    const response: ExtractResponse = {
      ...CLEAN_RESPONSE,
      confidence_threshold: 0.6,
      field_confidences: CLEAN_RESPONSE.field_confidences.map((f) =>
        f.field === 'source_name' ? { ...f, confidence: 0.8 } : f
      ),
    };
    const user = userEvent.setup();
    await runToReviewScreen(user, response);

    expect(screen.getByText('4 / 4 rules passed')).toBeInTheDocument();
  });
});
