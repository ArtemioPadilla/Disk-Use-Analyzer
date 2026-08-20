import { describe, it, expect } from 'vitest';
import { TIER_META, getTierBucket } from './tiers';

describe('TIER_META', () => {
  it('defines label, color and icon for all four tiers', () => {
    for (const tier of [1, 2, 3, 4]) {
      const meta = TIER_META[tier];
      expect(meta).toBeDefined();
      expect(meta.label).toBeTruthy();
      expect(meta.color).toMatch(/^#[0-9a-f]{6}$/i);
      expect(meta.icon).toBeTruthy();
    }
  });
});

describe('getTierBucket', () => {
  it('buckets tier 1 as safe', () => {
    expect(getTierBucket(1)).toBe('safe');
  });

  it('buckets tier 0 (or below) as safe too', () => {
    expect(getTierBucket(0)).toBe('safe');
  });

  it('buckets tier 2 as review', () => {
    expect(getTierBucket(2)).toBe('review');
  });

  it('buckets tier 3 as careful', () => {
    expect(getTierBucket(3)).toBe('careful');
  });

  it('buckets tier 4 as careful', () => {
    expect(getTierBucket(4)).toBe('careful');
  });

  it('buckets an unknown/large tier (missing-tier fallback) as careful', () => {
    expect(getTierBucket(9)).toBe('careful');
  });
});
