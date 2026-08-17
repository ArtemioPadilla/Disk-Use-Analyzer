import { describe, it, expect } from 'vitest';
import { formatAge, formatBytes } from './format';

describe('formatAge', () => {
  it('returns "Today" for 0 days', () => {
    expect(formatAge(0)).toBe('Today');
  });

  it('returns days for 1 day', () => {
    expect(formatAge(1)).toBe('1d');
  });

  it('switches to weeks at the 7-day boundary', () => {
    expect(formatAge(6)).toBe('6d');
    expect(formatAge(7)).toBe('1w');
  });

  it('switches to months at the 30-day boundary', () => {
    expect(formatAge(29)).toBe('4w');
    expect(formatAge(30)).toBe('1mo');
  });

  it('switches to years at the 365-day boundary', () => {
    expect(formatAge(364)).toBe('12mo');
    expect(formatAge(365)).toBe('1.0y');
  });

  it('formats multi-year ages with one decimal', () => {
    expect(formatAge(730)).toBe('2.0y');
  });
});

describe('formatBytes', () => {
  it('formats 0 bytes', () => {
    expect(formatBytes(0)).toBe('0 B');
  });

  it('formats bytes below 1 KB with no decimals', () => {
    expect(formatBytes(512)).toBe('512 B');
  });

  it('formats kilobytes with two decimals', () => {
    expect(formatBytes(1024)).toBe('1.00 KB');
  });

  it('formats megabytes', () => {
    expect(formatBytes(1024 * 1024 * 2.5)).toBe('2.50 MB');
  });

  it('formats gigabytes', () => {
    expect(formatBytes(1024 * 1024 * 1024)).toBe('1.00 GB');
  });
});
