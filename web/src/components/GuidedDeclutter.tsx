import { useState, useEffect, useMemo } from 'react';
import { on } from '../lib/events';
import { type SessionResults, type Recommendation } from '../lib/api';
import { formatBytes } from '../lib/format';
import { useCleanupRunner } from '../hooks/useCleanupRunner';

interface DeclutterStep {
  id: string;
  icon: string;
  title: string;
  description: string;
  items: Recommendation[];
  totalSpace: number;
}

export default function GuidedDeclutter() {
  const [active, setActive] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [steps, setSteps] = useState<DeclutterStep[]>([]);
  const [diskBefore, setDiskBefore] = useState(0);
  const [diskTotal, setDiskTotal] = useState(0);
  const { run, running, completed } = useCleanupRunner();

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => {
      const report = data.results?.[0]?.report;
      if (!report) return;

      const disk = report.summary?.disk_usage;
      if (disk) {
        setDiskBefore(disk.used);
        setDiskTotal(disk.total);
      }

      const recs = report.recommendations || [];
      const caches = report.cache_locations || [];

      // Build steps by category
      const builtSteps: DeclutterStep[] = [];

      // Step 1: Caches
      const cacheRecs = recs.filter(r => r.type?.toLowerCase().includes('cache') || r.description?.toLowerCase().includes('cache'));
      const cacheSize = caches.reduce((s, c) => s + (c.size || 0), 0);
      if (cacheSize > 0 || cacheRecs.length > 0) {
        builtSteps.push({
          id: 'caches', icon: '\u{1F5D1}️', title: 'Caches',
          description: 'System and app caches. These rebuild automatically when needed.',
          items: cacheRecs.length > 0 ? cacheRecs : recs.filter(r => (r.tier || 9) === 1).slice(0, 5),
          totalSpace: cacheSize || cacheRecs.reduce((s, r) => s + (r.space || 0), 0),
        });
      }

      // Step 2: Docker
      const dockerRecs = recs.filter(r => r.type?.toLowerCase().includes('docker') || r.command?.toLowerCase().includes('docker'));
      const dockerSpace = (report.docker as any)?.total_space || dockerRecs.reduce((s, r) => s + (r.space || 0), 0);
      if (dockerSpace > 0 || dockerRecs.length > 0) {
        builtSteps.push({
          id: 'docker', icon: '\u{1F433}', title: 'Docker',
          description: 'Unused images, stopped containers, and build cache.',
          items: dockerRecs.length > 0 ? dockerRecs : [{ tier: 2, priority: 'medium', type: 'docker', description: 'Prune unused Docker resources', space: dockerSpace, command: 'docker system prune -af' }],
          totalSpace: dockerSpace,
        });
      }

      // Step 3: Development (tier 1-2 dev-related)
      const devRecs = recs.filter(r =>
        r.description?.toLowerCase().match(/node_modules|npm|yarn|cargo|gradle|xcode|derived|simulator|homebrew|brew/) &&
        !r.type?.toLowerCase().includes('cache') && !r.type?.toLowerCase().includes('docker')
      );
      const devSpace = devRecs.reduce((s, r) => s + (r.space || 0), 0);
      if (devSpace > 0) {
        builtSteps.push({
          id: 'dev', icon: '\u{1F4BB}', title: 'Development Tools',
          description: 'Build artifacts, package caches, and old toolchain files.',
          items: devRecs, totalSpace: devSpace,
        });
      }

      // Step 4: Logs & misc (remaining tier 1-2)
      const usedIds = new Set([...cacheRecs, ...dockerRecs, ...devRecs].map(r => r.command));
      const remainingRecs = recs.filter(r => (r.tier || 9) <= 2 && r.command && !usedIds.has(r.command));
      const remainingSpace = remainingRecs.reduce((s, r) => s + (r.space || 0), 0);
      if (remainingSpace > 0) {
        builtSteps.push({
          id: 'other', icon: '\u{1F4CB}', title: 'Logs & Miscellaneous',
          description: 'System logs, temporary files, and other reclaimable space.',
          items: remainingRecs, totalSpace: remainingSpace,
        });
      }

      // Step 5: Review (tier 3-4). Excludes anything already placed in an
      // earlier step (e.g. tier 3-4 cache or Docker recs) — otherwise those
      // items get double-counted: once in their category step, once here.
      remainingRecs.forEach(r => usedIds.add(r.command));
      const reviewRecs = recs.filter(r => (r.tier || 9) >= 3 && r.command && !usedIds.has(r.command));
      const reviewSpace = reviewRecs.reduce((s, r) => s + (r.space || 0), 0);
      if (reviewSpace > 0) {
        builtSteps.push({
          id: 'review', icon: '⚠️', title: 'Review Carefully',
          description: 'These items may contain data you want to keep. Review before cleaning.',
          items: reviewRecs, totalSpace: reviewSpace,
        });
      }

      setSteps(builtSteps);
    });
    return off;
  }, []);

  // Total actually freed so far: sum of the space for every unique command,
  // across all steps, that the runner has confirmed exited with code 0.
  const freedTotal = useMemo(() => {
    const seen = new Set<string>();
    let total = 0;
    for (const step of steps) {
      for (const item of step.items) {
        if (item.command && completed.has(item.command) && !seen.has(item.command)) {
          seen.add(item.command);
          total += item.space || 0;
        }
      }
    }
    return total;
  }, [steps, completed]);

  const runnableCommands = (step: DeclutterStep) => step.items.filter(r => r.command && !r.command.startsWith('#'));
  const isStepCleaned = (step: DeclutterStep) => {
    const cmds = runnableCommands(step);
    return cmds.length > 0 && cmds.every(r => completed.has(r.command));
  };
  const isStepCleaning = (step: DeclutterStep) => runnableCommands(step).some(r => running.has(r.command));

  const cleanStep = (stepIndex: number) => {
    const step = steps[stepIndex];
    if (!step) return;
    for (const rec of runnableCommands(step)) {
      run({ command: rec.command, space: rec.space, label: rec.description });
    }
  };

  const startDeclutter = () => {
    setActive(true);
    setCurrentStep(0);
  };

  // Entry button (shown on cleanup page)
  if (!active) {
    return (
      <button className="btn btn-primary" onClick={startDeclutter}
        disabled={steps.length === 0}
        style={{ fontSize: '1rem', padding: '0.75rem 1.5rem', borderRadius: '12px', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        {'✨'} Guided Cleanup
        {steps.length > 0 && <span style={{ opacity: 0.8, fontSize: '0.8rem' }}>({steps.length} steps)</span>}
      </button>
    );
  }

  // Completion screen
  if (currentStep >= steps.length) {
    const pctBefore = diskTotal > 0 ? ((diskBefore / diskTotal) * 100).toFixed(0) : '?';
    const pctAfter = diskTotal > 0 ? (((diskBefore - freedTotal) / diskTotal) * 100).toFixed(0) : '?';
    return (
      <div style={{ textAlign: 'center', padding: '3rem 1rem' }}>
        <div style={{ fontSize: '4rem', marginBottom: '1rem' }}>{'\u{1F389}'}</div>
        <h2 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>Cleanup Complete!</h2>
        <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--success)', marginBottom: '0.5rem' }}>
          {formatBytes(freedTotal)} freed
        </div>
        <div style={{ color: 'var(--text-muted)', marginBottom: '2rem' }}>
          Disk usage: {pctBefore}% {'→'} {pctAfter}%
        </div>
        <button className="btn btn-ghost" onClick={() => setActive(false)}>Done</button>
      </div>
    );
  }

  const step = steps[currentStep];
  const isCleaned = isStepCleaned(step);
  const isCleaning = isStepCleaning(step);
  const projectedFreed = freedTotal + (isCleaned ? 0 : step.totalSpace);
  const projectedPct = diskTotal > 0 ? (((diskBefore - projectedFreed) / diskTotal) * 100).toFixed(0) : '?';

  return (
    <div>
      {/* Progress indicator */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '1.5rem' }}>
        {steps.map((s, i) => (
          <div key={s.id} style={{
            flex: 1, height: 4, borderRadius: 2,
            background: i < currentStep ? 'var(--success)' : i === currentStep ? 'var(--primary)' : 'var(--border)',
            transition: 'background 0.3s',
          }} />
        ))}
      </div>

      {/* Step header */}
      <div style={{ marginBottom: '1rem' }}>
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
          Step {currentStep + 1} of {steps.length}
        </div>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <span>{step.icon}</span> {step.title}
          <span style={{ fontSize: '1rem', fontWeight: 400, color: 'var(--primary)' }}>({formatBytes(step.totalSpace)})</span>
        </h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>{step.description}</p>
      </div>

      {/* Projected disk bar */}
      <div style={{ background: 'var(--card-bg)', border: '1px solid var(--border)', borderRadius: '8px', padding: '0.75rem', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.4rem' }}>
          <span>Projected after this step</span>
          <span>{projectedPct}% used</span>
        </div>
        <div style={{ height: 8, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{
            height: '100%', borderRadius: 4, transition: 'width 0.5s',
            width: `${projectedPct}%`,
            background: Number(projectedPct) > 90 ? 'var(--danger)' : Number(projectedPct) > 75 ? 'var(--warning)' : 'var(--success)',
          }} />
        </div>
      </div>

      {/* Items */}
      <div className="card" style={{ marginBottom: '1rem' }}>
        {step.items.map((item, i) => (
          <div key={i} style={{
            padding: '0.5rem 0',
            borderTop: i > 0 ? '1px solid var(--border)' : 'none',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <div style={{ fontSize: '0.85rem' }}>{item.description}</div>
            {item.space > 0 && <span style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-muted)', whiteSpace: 'nowrap', marginLeft: '1rem' }}>{formatBytes(item.space)}</span>}
          </div>
        ))}
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'space-between' }}>
        <button className="btn btn-ghost" onClick={() => setCurrentStep(prev => prev + 1)}>
          Skip {'→'}
        </button>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {isCleaned ? (
            <span style={{ color: 'var(--success)', fontWeight: 600, display: 'flex', alignItems: 'center' }}>{'✓'} Cleaned</span>
          ) : (
            <button className="btn btn-primary" onClick={() => cleanStep(currentStep)} disabled={isCleaning}
              style={{ fontSize: '0.95rem' }}>
              {isCleaning ? 'Cleaning...' : `Clean ${step.title} (${formatBytes(step.totalSpace)})`}
            </button>
          )}
          <button className="btn btn-ghost" onClick={() => setCurrentStep(prev => prev + 1)}>
            Next {'→'}
          </button>
        </div>
      </div>

      {/* Running total */}
      {freedTotal > 0 && (
        <div style={{ textAlign: 'center', marginTop: '1.5rem', color: 'var(--success)', fontWeight: 600 }}>
          Total freed so far: {formatBytes(freedTotal)}
        </div>
      )}
    </div>
  );
}
