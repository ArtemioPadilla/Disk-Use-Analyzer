import { describe, it, expect } from 'vitest';
import { getCategory, CATEGORY_COLORS } from './categories';

describe('getCategory', () => {
  it.each([
    ['/Users/me/project/node_modules/react/index.js', 'Development'],
    ['/Users/me/.npm/_cacache/blah', 'Development'],
    ['/Users/me/.cargo/registry/src/foo', 'Development'],
    ['/Users/me/.rustup/toolchains/stable', 'Development'],
    ['/Users/me/.gradle/caches/modules', 'Development'],
    ['/Users/me/Developer/repos/foo', 'Development'],
    ['/Users/me/Library/Containers/com.docker.docker/Data/vms/0/docker.raw', 'Docker'],
    ['/Users/me/Library/Caches/some-app/cache/data.db', 'Caches & Logs'],
    ['/private/tmp/some-file', 'Caches & Logs'],
    ['/Users/me/Library/Logs/DiagnosticReports/crash.log', 'Caches & Logs'],
    ['/Users/me/Library/Application Support/Foo', 'System Library'],
    ['/Users/me/Documents/report.pdf', 'Documents'],
    ['/Users/me/Desktop/notes.txt', 'Documents'],
    ['/Users/me/Downloads/installer.dmg', 'Documents'],
    ['/Users/me/Movies/video.mp4', 'Media'],
    ['/Users/me/Pictures/photo.JPG', 'Media'],
    ['/Users/me/random/thing.txt', 'Other'],
  ])('classifies %s as %s', (path, expected) => {
    expect(getCategory(path)).toBe(expected);
  });

  it('is case-insensitive on the path', () => {
    expect(getCategory('/USERS/ME/NODE_MODULES/FOO')).toBe('Development');
  });
});

describe('CATEGORY_COLORS', () => {
  it('has a color for every category getCategory can return', () => {
    const categories = ['Development', 'Docker', 'Caches & Logs', 'System Library', 'Documents', 'Media', 'Other'];
    for (const cat of categories) {
      expect(CATEGORY_COLORS[cat]).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });
});
