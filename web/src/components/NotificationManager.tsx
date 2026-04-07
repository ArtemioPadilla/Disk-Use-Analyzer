import { useEffect, useRef } from 'react';
import { on } from '../lib/events';
import { formatBytes } from '../lib/format';

export default function NotificationManager() {
  const permissionRef = useRef<NotificationPermission>('default');

  useEffect(() => {
    if ('Notification' in window) {
      permissionRef.current = Notification.permission;
    }

    const offs = [
      on('analysis:started', () => {
        // Request permission when analysis starts (needs user gesture context,
        // but this is close enough — triggered by button click)
        if ('Notification' in window && permissionRef.current === 'default') {
          Notification.requestPermission().then(p => {
            permissionRef.current = p;
          });
        }
      }),
      on('analysis:completed', (data: any) => {
        if ('Notification' in window && permissionRef.current === 'granted') {
          const summary = data.results?.[0]?.report?.summary;
          const recoverable = summary?.recoverable_space;
          const files = summary?.files_scanned;

          new Notification('Disk Analysis Complete', {
            body: recoverable
              ? `Found ${formatBytes(recoverable)} recoverable space across ${files?.toLocaleString() || '?'} files`
              : 'Analysis finished successfully',
            icon: '/favicon.svg',
          });
        }
      }),
    ];
    return () => offs.forEach(off => off());
  }, []);

  return null; // headless component
}
