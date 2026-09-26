use sysinfo::Disks;

#[derive(Debug, Clone, Copy)]
pub struct DiskUsage {
    pub total: u64,
    pub used: u64,
    /// Strictly free bytes, as `statvfs` reports them. What alerts use.
    pub available: u64,
    /// Space macOS can reclaim on its own when it needs to (caches, local
    /// snapshots, leftovers of an OS update). Shown, never counted as free.
    pub purgeable: u64,
    pub percent: f64,
}

/// Strictly free and total bytes for `/`, from `statvfs`.
///
/// This is the same call the Python engine makes (`shutil.disk_usage`), so the
/// tray and the web UI agree by construction. They used not to: `sysinfo`
/// reports macOS's "available for important usage", which includes purgeable
/// space. With next to none purgeable that made no difference; after the
/// upgrade to macOS 27 the development machine had 5.5 GB purgeable, the tray
/// said 19.6 GB free while the web said 14.0, and tests/consistency.rs failed.
fn statvfs_raiz() -> Option<(u64, u64)> {
    let mut st: libc::statvfs = unsafe { std::mem::zeroed() };
    let r = unsafe { libc::statvfs(c"/".as_ptr(), &mut st) };
    if r != 0 {
        return None;
    }
    let bloque = st.f_frsize as u64;
    Some((st.f_blocks as u64 * bloque, st.f_bavail as u64 * bloque))
}

/// Read usage for the volume backing `/`.
///
/// `used` is deliberately computed as `total - available` rather than taken
/// from any per-volume "used" figure: on APFS the root volume is read-only
/// and its own used bytes say nothing about how full the disk is. The Python
/// engine made this same choice (`disk_analyzer_core.get_disk_usage`), and
/// tests/consistency.rs fails if the two ever drift apart.
///
/// `available` is the strict figure, not the one that counts purgeable space:
/// macOS reclaims purgeable space when it decides to, not when the user needs
/// it, and a low-disk warning has to err on the early side.
pub fn read() -> Option<DiskUsage> {
    let (total, available) = statvfs_raiz()?;
    if total == 0 {
        return None;
    }
    // sysinfo gives "available for important usage", which includes what is
    // purgeable; the difference with the strict figure is the purgeable part.
    let importante = Disks::new_with_refreshed_list()
        .list()
        .iter()
        .find(|d| d.mount_point() == std::path::Path::new("/"))
        .map(|d| d.available_space())
        .unwrap_or(available);
    let used = total.saturating_sub(available);
    Some(DiskUsage {
        total,
        used,
        available,
        purgeable: importante.saturating_sub(available),
        percent: used as f64 / total as f64 * 100.0,
    })
}
