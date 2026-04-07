import { useState, useEffect, useRef } from 'react';
import { on, emit } from '../lib/events';
import { useTerminal } from '../hooks/useTerminal';

export default function FloatingTerminal() {
  const [visible, setVisible] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [position, setPosition] = useState({ x: -1, y: -1 });
  const termRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<any>(null);
  const fitAddonRef = useRef<any>(null);
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);
  const { ptyId, connected, spawn, send, resize, kill, onDataRef } = useTerminal();

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

      // Need to import CSS for xterm
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.min.css';
      document.head.appendChild(link);

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
    }
  }, [visible]);

  // Resize observer
  useEffect(() => {
    if (!fitAddonRef.current || !termRef.current) return;
    const observer = new ResizeObserver(() => fitAddonRef.current?.fit());
    observer.observe(termRef.current);
    return () => observer.disconnect();
  }, [visible, minimized]);

  // Event listeners
  useEffect(() => {
    const offs = [
      on('terminal:toggle', () => { setVisible(v => !v); setMinimized(false); }),
      on('terminal:open', async (data: { pty_id?: string; command?: string }) => {
        setVisible(true);
        setMinimized(false);
        if (!ptyId) await spawn(data.command);
      }),
    ];
    return () => offs.forEach(off => off());
  }, [ptyId, spawn]);

  // Auto-spawn on first open
  useEffect(() => {
    if (visible && !minimized && !ptyId) spawn();
  }, [visible, minimized, ptyId, spawn]);

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
