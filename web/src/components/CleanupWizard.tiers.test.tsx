import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/react';
import { act } from '@testing-library/react';
import { nivelDe } from './CleanupWizard';
import CleanupWizard from './CleanupWizard';

vi.mock('../hooks/useCleanupRunner', () => ({
  useCleanupRunner: vi.fn(() => ({ run: vi.fn(), running: new Set(), completed: new Set() })),
}));

describe('nivelDe', () => {
  it('respeta el nivel cuando viene', () => {
    expect(nivelDe({ tier: 1 })).toBe(1);
    expect(nivelDe({ tier: 3 })).toBe(3);
  });

  it('trata lo desconocido como lo más restrictivo, no como Seguro', () => {
    for (const rec of [{}, { tier: undefined }, { tier: null }, { tier: 0 },
                       { tier: NaN }, { tier: 'dos' }, { tier: 9 }]) {
      expect(nivelDe(rec as any)).toBe(4);
    }
  });
});

describe('CleanupWizard component: malformed recommendations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('does not count malformed recommendations as safe', async () => {
    // One legitimate tier-1 recommendation (100 bytes)
    // Three malformed recommendations: no tier, tier: null, tier: 0 (100 bytes each)
    // Without the fix, all four would be treated as tier 1 (total 400)
    // With the fix, only the legitimate one counts (total 100)
    const recs = [
      { description: 'Safe item', command: 'rm x', space: 100, tier: 1, priority: 'low', type: 'cache' },
      { description: 'Malformed (no tier)', command: 'rm y', space: 100, priority: 'low', type: 'cache' },
      { description: 'Malformed (null)', command: 'rm z', space: 100, tier: null as any, priority: 'low', type: 'cache' },
      { description: 'Malformed (0)', command: 'rm w', space: 100, tier: 0, priority: 'low', type: 'cache' },
    ] as any;

    render(<CleanupWizard />);

    // Emit the analysis:completed event with mixed recommendations
    act(() => {
      window.dispatchEvent(new CustomEvent('analysis:completed', {
        detail: {
          results: [
            { report: { recommendations: recs } },
          ],
        },
      }));
    });

    // Wait for recommendations to be rendered
    await waitFor(
      () => {
        const allText = document.body.textContent || '';
        // This will throw if not found, which is what waitFor expects
        if (!allText.includes('Safe item')) {
          throw new Error('Safe item not found');
        }
      },
      { timeout: 2000 }
    );

    // Get all text for verification
    const allText = document.body.textContent || '';

    // Verify Tier 1 has exactly 1 item and 100 B (not 4 items and 400 B)
    expect(allText).toContain('1 items · 100 B');

    // Verify Tier 4 has exactly 3 items and 300 B
    expect(allText).toContain('3 items · 300 B');

    // Most importantly: verify that there is no "4 items · 400 B" which would indicate
    // all recommendations were counted as Tier 1 due to the bug (r.tier || 1)
    expect(allText).not.toContain('4 items · 400 B');
  });
});
