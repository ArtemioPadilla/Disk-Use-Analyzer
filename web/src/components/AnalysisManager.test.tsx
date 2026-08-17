import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/react';
import AnalysisManager from './AnalysisManager';
import { api } from '../lib/api';

// This suite only covers the mount-time reattach logic added for Task 4: a
// full page navigation remounts AnalysisManager with sessionId = null (see
// its own module comment), so on mount it asks the server whether an
// analysis is already running and, if so, reconnects to it. The rest of the
// component (the WebSocket message handling itself) is unit-testable in
// principle but would need a much larger fake-server harness than this
// change warrants — this suite deliberately stays scoped to the reattach
// decision, which is the pure/decidable part.
vi.mock('../lib/api', () => ({
  api: { getSessions: vi.fn(), startAnalysis: vi.fn() },
}));

const mockedGetSessions = vi.mocked(api.getSessions);

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: any }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
  close() { this.closed = true; }
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeWebSocket.instances = [];
  (globalThis as any).WebSocket = FakeWebSocket;
});

afterEach(() => {
  cleanup();
});

describe('AnalysisManager reattach on mount', () => {
  it('reconnects to a session the server reports as running', async () => {
    mockedGetSessions.mockResolvedValue({
      sessions: [
        { id: 'sess-running', status: 'running', progress: 40, current_path: '/x', paths: ['~'], started_at: '2026-01-01T00:00:00Z' },
        { id: 'sess-old', status: 'completed', progress: 100, current_path: '', paths: ['~'], started_at: '2025-12-01T00:00:00Z' },
      ],
    } as any);

    render(<AnalysisManager />);

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    expect(FakeWebSocket.instances[0].url).toContain('/ws/sess-running');
  });

  it('does nothing when no session is running', async () => {
    mockedGetSessions.mockResolvedValue({
      sessions: [
        { id: 'sess-done', status: 'completed', progress: 100, current_path: '', paths: ['~'], started_at: '2025-12-01T00:00:00Z' },
      ],
    } as any);

    render(<AnalysisManager />);

    await waitFor(() => expect(mockedGetSessions).toHaveBeenCalledTimes(1));
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it('fails quietly when the sessions request errors', async () => {
    mockedGetSessions.mockRejectedValue(new Error('network down'));

    expect(() => render(<AnalysisManager />)).not.toThrow();

    await waitFor(() => expect(mockedGetSessions).toHaveBeenCalledTimes(1));
    expect(FakeWebSocket.instances).toHaveLength(0);
  });
});
