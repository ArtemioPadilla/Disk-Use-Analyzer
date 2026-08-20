/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    // Only our own sources — never the Astro build output.
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
