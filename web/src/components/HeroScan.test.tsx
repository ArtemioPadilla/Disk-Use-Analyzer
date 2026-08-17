import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/react';
import HeroScan from './HeroScan';
import { api } from '../lib/api';

// Covers the Task 4b fix: when SessionList navigates here with
// ?session=<id> (see HeroScan's own module comment) and the backend no
// longer has that session's results on disk (MAX_STORED_RESULTS keeps only
// the 10 most recent, while session *metadata* lives longer — see
// disk_analyzer_web.py), api.getResults rejects. Before this fix that just
// fell through to the same silent "Analyze Your Disk" onboarding screen as
// a fresh install, with no indication anything was even requested. Now a
// persistent inline message explains it. The ordinary no-?session path must
// keep behaving exactly as before (no message).
vi.mock('../lib/api', () => ({
  api: { getResults: vi.fn(), getSystemInfo: vi.fn() },
}));

const mockedGetResults = vi.mocked(api.getResults);

beforeEach(() => {
  vi.clearAllMocks();
  // Reset to a clean URL before each test; individual tests opt into
  // ?session=<id> via pushState.
  window.history.pushState({}, '', '/');
  // No-param path falls through to this fetch; keep it quiet/failing so it
  // resolves to the ordinary "no results" state without a console warning.
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 404, ok: false }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('HeroScan requested-session handling', () => {
  it('shows a persistent message when the requested session\'s results are gone', async () => {
    window.history.pushState({}, '', '/?session=sess-gone');
    mockedGetResults.mockRejectedValue(new Error('API 410: gone'));

    const { findByRole } = render(<HeroScan />);

    const alert = await findByRole('alert');
    expect(alert.textContent).toMatch(/no longer stored/i);
    expect(alert.textContent).toMatch(/10 most recent/i);
    // Falls through to the same onboarding CTA as the empty-history case.
    expect(await findByRole('button', { name: /scan my mac/i })).toBeTruthy();
  });

  it('does not show the message when no session was requested', async () => {
    mockedGetResults.mockRejectedValue(new Error('should not be called'));

    const { findByRole, queryByRole } = render(<HeroScan />);

    await findByRole('button', { name: /scan my mac/i });
    expect(queryByRole('alert')).toBeNull();
    expect(mockedGetResults).not.toHaveBeenCalled();
  });

  it('does not show the message when the requested session loads successfully', async () => {
    window.history.pushState({}, '', '/?session=sess-ok');
    mockedGetResults.mockResolvedValue({ id: 'sess-ok', status: 'completed', results: [] });

    const { container } = render(<HeroScan />);

    await waitFor(() => expect(mockedGetResults).toHaveBeenCalledWith('sess-ok'));
    // Results found: HeroScan yields to the dashboard components (renders null).
    await waitFor(() => expect(container.firstChild).toBeNull());
  });
});
