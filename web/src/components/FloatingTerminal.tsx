import { useState, useEffect, useRef } from 'react';
import '@xterm/xterm/css/xterm.css';
import { on } from '../lib/events';
import { useTerminal } from '../hooks/useTerminal';

export default function FloatingTerminal() {
  const [visible, setVisible] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [xtermReady, setXtermReady] = useState(false);
  const [position, setPosition] = useState({ x: -1, y: -1 });
  const termRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<any>(null);
  const fitAddonRef = useRef<any>(null);
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);
  const { ptyId, connected, spawn, attach, send, resize, kill, onDataRef } = useTerminal();

  // Initialize position on first show
  useEffect(() => {
    if (visible && position.x === -1) {
      setPosition({ x: window.innerWidth - 620, y: window.innerHeight - 340 });
    }
  }, [visible]);

  // Initialize xterm.js when terminal becomes visible and not minimized
  useEffect(() => {
    if (!visible || minimized || !termRef.current || xtermRef.current) return;

    let cancelled = false;

    Promise.all([
      import('@xterm/xterm'),
      import('@xterm/addon-fit'),
    ]).then(([xtermModule, fitModule]) => {
      if (cancelled || !termRef.current) return;

      const term = new xtermModule.Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: 'Menlo, Monaco, monospace',
        theme: {
          background: '#1f2937',
          foreground: '#d1d5db',
          cursor: '#10b981',
          selectionBackground: '#6366f140',
        },
        cols: 80,
        rows: 20,
      });

      const fitAddon = new fitModule.FitAddon();
      term.loadAddon(fitAddon);
      term.open(termRef.current);
      fitAddon.fit();

      xtermRef.current = term;
      fitAddonRef.current = fitAddon;

      term.onData((data: string) => send(data));
      onDataRef.current = (data: string | ArrayBuffer) => {
        if (data instanceof ArrayBuffer) term.write(new Uint8Array(data));
        else term.write(data);
      };

      resize(term.cols, term.rows);
      term.onResize(({ cols, rows }: { cols: number; rows: number }) => resize(cols, rows));

      // fitAddonRef is only populated here, inside this async .then() — the
      // resize-observer effect below depends on xtermReady so it re-runs
      // once the ref actually has a value instead of only on visible/minimized.
      setXtermReady(true);
    });

    return () => { cancelled = true; };
  }, [visible, minimized, send, resize]);

  // Cleanup xterm on hide
  useEffect(() => {
    if (!visible && xtermRef.current) {
      xtermRef.current.dispose();
      xtermRef.current = null;
      fitAddonRef.current = null;
      onDataRef.current = null;
      setXtermReady(false);
    }
  }, [visible]);

  // Resize observer
  useEffect(() => {
    if (!fitAddonRef.current || !termRef.current) return;
    const observer = new ResizeObserver(() => fitAddonRef.current?.fit());
    observer.observe(termRef.current);
    return () => observer.disconnect();
  }, [visible, minimized, xtermReady]);

  // Event listeners
  useEffect(() => {
    const offs = [
      on('terminal:toggle', () => { setVisible(v => !v); setMinimized(false); }),
      on('terminal:open', async (data: { pty_id?: string; command?: string }) => {
        setVisible(true);
        setMinimized(false);
        if (data.pty_id) {
          // A specific PTY was already created elsewhere (e.g. a cleanup
          // command run through useCleanupRunner) — show that exact session
          // instead of spawning a second, invisible one running the same
          // command. Switch to it even if a different terminal is already
          // showing, rather than silently ignoring the request.
          if (data.pty_id !== ptyId) attach(data.pty_id, data.command);
        } else if (!ptyId) {
          // Manual open (the ⚡ button) with no target PTY: start a plain shell.
          await spawn(data.command);
        }
      }),
    ];
    return () => offs.forEach(off => off());
  }, [ptyId, spawn, attach]);

  // Auto-spawn on first open
  useEffect(() => {
    if (visible && !minimized && !ptyId) spawn();
  }, [visible, minimized, ptyId, spawn]);

  // useTerminal reattaches to a still-alive PTY on mount (see useTerminal.ts)
  // without going through terminal:open — so if that reattach set a ptyId
  // and this widget isn't showing yet, surface it. This is what makes the
  // terminal survive a page navigation instead of reconnecting invisibly.
  useEffect(() => {
    if (ptyId && !visible) setVisible(true);
  }, [ptyId]);

  // Drag handlers
  const onDragStart = (e: React.MouseEvent) => {
    dragRef.current = { startX: e.clientX, startY: e.clientY, origX: position.x, origY: position.y };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      setPosition({ x: dragRef.current.origX + (ev.clientX - dragRef.current.startX), y: dragRef.current.origY + (ev.clientY - dragRef.current.startY) });
    };
    const onUp = () => { dragRef.current = null; window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  if (!visible) return null;

  return (
    <div style={{
      position: 'fixed', left: position.x, top: position.y,
      width: minimized ? 280 : 600, zIndex: 9999,
      background: '#1f2937', borderRadius: '10px',
      boxShadow: '0 8px 30px rgba(0,0,0,0.35)', overflow: 'hidden',
      resize: minimized ? 'none' : 'both', minWidth: 300, minHeight: minimized ? 36 : 200,
    }}>
      <div onMouseDown={onDragStart} style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '0.4rem 0.75rem', background: '#111827', cursor: 'move', userSelect: 'none',
      }}>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', fontSize: '0.75rem', color: '#9ca3af' }}>
          <span style={{ color: '#10b981', fontWeight: 600 }}>&#9889; Terminal</span>
          {connected && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981', display: 'inline-block' }} />}
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.8rem', color: '#9ca3af' }}>
          <span onClick={() => setMinimized(m => !m)} style={{ cursor: 'pointer' }} title="Minimize">&#9472;</span>
          <span onClick={async () => { await kill(); setVisible(false); }} style={{ cursor: 'pointer' }} title="Close">&#10005;</span>
        </div>
      </div>
      {!minimized && <div ref={termRef} style={{ padding: '4px', height: 'calc(100% - 36px)' }} />}
    </div>
  );
}
