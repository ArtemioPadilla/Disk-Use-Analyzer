import { describe, it, expect } from 'vitest';
import { nivelDe } from './CleanupWizard';

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
