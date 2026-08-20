import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import { authHeaders, notifyAuthInvalid } from '../lib/auth';
import { on, emit } from '../lib/events';

export default function HeroScan() {
  const [hasResults, setHasResults] = useState<boolean | null>(null);
  const [scanning, setScanning] = useState(false);
  // Set only when a specific ?session=<id> was requested (SessionList's
  // "Load Results") and fetching its results failed. The backend only keeps
  // MAX_STORED_RESULTS (10) result files on disk while session *metadata*
  // sticks around for longer, so a session that still shows as "completed"
  // in History can 410 here. Distinct from the ordinary no-param case, which
  // must keep rendering the plain "nothing scanned yet" empty state below.
  const [sessionUnavailable, setSessionUnavailable] = useState(false);

  useEffect(() => {
    // SessionList navigates here with ?session=<id> instead of dispatching
    // an event directly, since a full page navigation would kill the event
    // before this component could mount and receive it. If a specific
    // session was requested, load exactly that one instead of falling back
    // to whatever is most recent.
    const params = new URLSearchParams(window.location.search);
    const requested = params.get('session');

    if (requested) {
      api.getResults(requested).then(data => {
        setHasResults(true);
        emit('analysis:completed', data);
      }).catch(() => {
        // api.getResults already calls notifyAuthInvalid() on a 401; any
        // other failure (410 gone, 404, etc.) falls through to the same
        // "no results" rendering as the no-param case below, but — unlike
        // that case — we know exactly why: the user asked for this session
        // and it isn't there. Say so instead of silently looking like a
        // fresh install (see module comment).
        setSessionUnavailable(true);
        setHasResults(false);
      });
      return;
    }

    // No specific session requested: check if there are any completed
    // results, exactly as before.
    fetch('/api/analysis/latest', { headers: authHeaders() }).then(r => {
      if (r.status === 401) {
        // This is the canonical "dashboard renders empty with no message"
        // case: a stale token makes this look like "no results yet" instead
        // of the actual problem. Notify, but still fall through to the
        // existing hasResults=false rendering below — the banner explains
        // the real state on top of it.
        notifyAuthInvalid();
        setHasResults(false);
        return;
      }
      if (r.ok) {
        r.json().then(data => {
          setHasResults(true);
          // Broadcast so other components load the data
          emit('analysis:completed', data);
        });
      } else {
        setHasResults(false);
      }
    }).catch(() => setHasResults(false));

    const offs = [
      on('analysis:started', () => setScanning(true)),
      on('analysis:completed', () => { setHasResults(true); setScanning(false); }),
      on('analysis:error', () => setScanning(false)),
    ];
    return () => offs.forEach(off => off());
  }, []);

  if (hasResults === null) return null; // loading
  if (hasResults) return null; // results exist, dashboard components handle it

  const startQuickScan = async () => {
    const info = await api.getSystemInfo();
    const minSize = Number(localStorage.getItem('disk-analyzer-min-size') ?? info.default_min_size_mb ?? 10);
    // Use ~ expansion - the backend handles it
    emit('analysis:start-request', { paths: ['~'], minSizeMb: minSize });
  };

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      minHeight: '60vh', textAlign: 'center', padding: '2rem',
    }}>
      {sessionUnavailable && (
        // Persistent, not a toast: the empty state below stays on screen
        // indefinitely (there's no follow-up event that would make a 4s
        // auto-dismiss timely), so the explanation needs to stay put too —
        // same reasoning as AuthErrorBanner. Kept inline here rather than
        // as a fixed top banner since it's specific to *this* empty state,
        // not an app-wide condition.
        <div role="alert" style={{
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          background: 'var(--card-bg)', border: '1px solid var(--warning)',
          borderLeft: '4px solid var(--warning)', borderRadius: '8px',
          padding: '0.75rem 1rem', marginBottom: '1.5rem',
          fontSize: '0.85rem', maxWidth: '440px', textAlign: 'left',
        }}>
          <span>
            This analysis is no longer stored &mdash; only the 10 most recent results are kept.
            Run a new scan to see current data.
          </span>
        </div>
      )}
      <div style={{ fontSize: '4rem', marginBottom: '1rem' }}>&#x1F4BF;</div>
      <h2 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '0.5rem' }}>
        {scanning ? 'Scanning your Mac...' : 'Analyze Your Disk'}
      </h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: '2rem', maxWidth: '400px' }}>
        {scanning
          ? 'This may take a few minutes. You can watch progress above.'
          : "Find out what's eating your disk space. One click to scan your home directory."}
      </p>
      {!scanning && (
        <>
          <button className="btn btn-primary" onClick={startQuickScan}
            style={{ fontSize: '1.1rem', padding: '0.75rem 2rem', borderRadius: '12px' }}>
            Scan My Mac
          </button>
          <button className="btn btn-ghost" onClick={() => emit('analysis:new')}
            style={{ marginTop: '0.75rem', fontSize: '0.85rem' }}>
            Advanced options...
          </button>
        </>
      )}
      {scanning && (
        <div style={{
          width: 40, height: 40, border: '3px solid var(--border)',
          borderTopColor: 'var(--primary)', borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
        }} />
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
