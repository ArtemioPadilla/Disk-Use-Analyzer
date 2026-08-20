use sysinfo::Disks;

#[derive(Debug, Clone, Copy)]
pub struct DiskUsage {
    pub total: u64,
    pub used: u64,
    pub available: u64,
    pub percent: f64,
}

/// Read usage for the volume backing `/`.
///
/// `used` is deliberately computed as `total - available` rather than taken
/// from any per-volume "used" figure: on APFS the root volume is read-only
/// and its own used bytes say nothing about how full the disk is. The Python
/// engine made this same choice (`disk_analyzer_core.get_disk_usage`), and
/// tests/consistency.rs fails if the two ever drift apart.
pub fn read() -> Option<DiskUsage> {
    let disks = Disks::new_with_refreshed_list();
    let root = disks
        .list()
        .iter()
        .find(|d| d.mount_point() == std::path::Path::new("/"))?;

    let total = root.total_space();
    let available = root.available_space();
    if total == 0 {
        return None;
    }
    let used = total.saturating_sub(available);
    Some(DiskUsage {
        total,
        used,
        available,
        percent: used as f64 / total as f64 * 100.0,
    })
}
