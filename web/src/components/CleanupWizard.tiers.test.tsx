import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, cleanup, waitFor, screen, fireEvent } from '@testing-library/react';
import { act } from '@testing-library/react';
import { nivelDe } from './CleanupWizard';
import CleanupWizard from './CleanupWizard';
import { useCleanupRunner } from '../hooks/useCleanupRunner';

const mockRun = vi.fn();

vi.mock('../hooks/useCleanupRunner', () => ({
  useCleanupRunner: vi.fn(() => ({ run: mockRun, running: new Set(), completed: new Set() })),
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

  it('safeTotalSpace does not include malformed recommendations', async () => {
    // Verifies line 50: safeTotalSpace calculation. Observable in button label without clicking.
    const recs = [
      { description: 'Safe item', command: 'rm x', space: 100, tier: 1, priority: 'low', type: 'cache' },
      { description: 'Malformed (no tier)', command: 'rm y', space: 100, priority: 'low', type: 'cache' },
      { description: 'Malformed (null)', command: 'rm z', space: 100, tier: null as any, priority: 'low', type: 'cache' },
      { description: 'Malformed (0)', command: 'rm w', space: 100, tier: 0, priority: 'low', type: 'cache' },
    ] as any;

    render(<CleanupWizard />);

    act(() => {
      window.dispatchEvent(new CustomEvent('analysis:completed', {
        detail: { results: [{ report: { recommendations: recs } }] },
      }));
    });

    await waitFor(
      () => {
        if (!document.body.textContent?.includes('Safe item')) {
          throw new Error('Safe item not found');
        }
      },
      { timeout: 2000 }
    );

    // The "Clean Safe Items" button should show "(100 B)" not "(400 B)"
    // This protects line 50: safeTotalSpace = recs.filter(r => nivelDe(r) === 1)...
    const buttonText = screen.getByText(/Clean Safe Items/).textContent;
    expect(buttonText).toContain('(100 B)');
    expect(buttonText).not.toContain('(400 B)');
  });

  it('cleanSafeItems only executes legitimate safe recommendations', async () => {
    // Verifies line 53: safeRecs filtering in cleanSafeItems(). Protects what actually gets deleted.
    // This is the critical path: line 53 decides what run() gets called with.
    const recs = [
      { description: 'Safe item', command: 'rm x', space: 100, tier: 1, priority: 'low', type: 'cache' },
      { description: 'Malformed (no tier)', command: 'rm y', space: 100, priority: 'low', type: 'cache' },
      { description: 'Malformed (null)', command: 'rm z', space: 100, tier: null as any, priority: 'low', type: 'cache' },
      { description: 'Malformed (0)', command: 'rm w', space: 100, tier: 0, priority: 'low', type: 'cache' },
    ] as any;

    render(<CleanupWizard />);

    act(() => {
      window.dispatchEvent(new CustomEvent('analysis:completed', {
        detail: { results: [{ report: { recommendations: recs } }] },
      }));
    });

    await waitFor(
      () => {
        if (!document.body.textContent?.includes('Safe item')) {
          throw new Error('Safe item not found');
        }
      },
      { timeout: 2000 }
    );

    // Click the "Clean Safe Items" button
    const button = screen.getByText(/Clean Safe Items/);
    fireEvent.click(button);

    // run() should be called exactly once (only for the legitimate safe recommendation)
    // If line 53 were using r.tier || 1, it would call run() 4 times
    expect(mockRun).toHaveBeenCalledTimes(1);
    expect(mockRun).toHaveBeenCalledWith(
      expect.objectContaining({
        command: 'rm x',
        space: 100,
        label: 'Safe item',
      })
    );
  });

  it('does not count malformed recommendations as safe (visual grouping)', async () => {
    // Verifies line 63: tier assignment for visual grouping. Less critical but good to have.
    const recs = [
      { description: 'Safe item', command: 'rm x', space: 100, tier: 1, priority: 'low', type: 'cache' },
      { description: 'Malformed (no tier)', command: 'rm y', space: 100, priority: 'low', type: 'cache' },
      { description: 'Malformed (null)', command: 'rm z', space: 100, tier: null as any, priority: 'low', type: 'cache' },
      { description: 'Malformed (0)', command: 'rm w', space: 100, tier: 0, priority: 'low', type: 'cache' },
    ] as any;

    render(<CleanupWizard />);

    act(() => {
      window.dispatchEvent(new CustomEvent('analysis:completed', {
        detail: { results: [{ report: { recommendations: recs } }] },
      }));
    });

    await waitFor(
      () => {
        if (!document.body.textContent?.includes('Safe item')) {
          throw new Error('Safe item not found');
        }
      },
      { timeout: 2000 }
    );

    const allText = document.body.textContent || '';

    // Verify visual grouping is correct
    expect(allText).toContain('1 items · 100 B');
    expect(allText).toContain('3 items · 300 B');
    expect(allText).not.toContain('4 items · 400 B');
  });
});
