// Single source of truth for cleanup risk-tier metadata. Previously
// duplicated (and disagreeing) across CleanupWizard.tsx, WhatIfSandbox.tsx
// and ReverseView.tsx.

export interface TierMeta {
  label: string;
  color: string;
  icon: string;
}

export const TIER_META: Record<number, TierMeta> = {
  1: { label: 'Safe', color: '#10b981', icon: '✅' },
  2: { label: 'Moderate', color: '#f59e0b', icon: '⚠️' },
  3: { label: 'Aggressive', color: '#ef4444', icon: '🔴' },
  4: { label: 'Deep Clean', color: '#7c3aed', icon: '💀' },
};

/**
 * Collapses the four numeric risk tiers into the three buckets used by the
 * ReverseView "what can I safely delete" summary: tier 1 is safe, tier 2
 * needs a quick review, and tiers 3-4 need care before running.
 */
export function getTierBucket(tier: number): 'safe' | 'review' | 'careful' {
  if (tier <= 1) return 'safe';
  if (tier === 2) return 'review';
  return 'careful';
}
