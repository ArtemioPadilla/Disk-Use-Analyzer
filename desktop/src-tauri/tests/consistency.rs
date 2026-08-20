use std::process::Command;

/// The tray must show the same number as the rest of the project.
/// Measured on this machine while writing the plan: the engine reports
/// 96.6% used while `df`'s own "used" column reports 43% -- a 53-point gap,
/// because on APFS `/` is the read-only system volume while free space
/// belongs to the shared container. Reading disk usage the way `df` does
/// would make the tray show a reassuring green on a nearly-full disk.
#[test]
fn rust_reading_matches_the_python_engine() {
    let repo = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .expect("repo root");

    let out = Command::new(repo.join("venv-web/bin/python"))
        .current_dir(&repo)
        .args([
            "-c",
            "import sys; sys.path.insert(0,'.'); \
             from disk_analyzer_core import DiskAnalyzerCore; \
             d=DiskAnalyzerCore('.').get_disk_usage(); \
             print(d['total'], d['used'], d['available'])",
        ])
        .output()
        .expect("the python engine must be runnable");

    let stdout = String::from_utf8(out.stdout).expect("utf8");
    let nums: Vec<u64> = stdout
        .split_whitespace()
        .map(|s| s.parse().expect("number"))
        .collect();
    let (py_total, py_used, py_available) = (nums[0], nums[1], nums[2]);

    let rust = desktop_lib::disk::read().expect("disk read");

    // Free space moves while the test runs, so compare with a tolerance
    // large enough for normal churn but far smaller than the 53-point gap
    // this test exists to catch.
    let tolerance = (py_total as f64 * 0.01) as u64; // 1% of the volume
    assert!(
        rust.total.abs_diff(py_total) <= tolerance,
        "el total diverge: rust {} vs python {}", rust.total, py_total
    );
    assert!(
        rust.used.abs_diff(py_used) <= tolerance,
        "used diverge: rust {} vs python {} -- ¿estás usando la columna 'used' \
         en vez de total-available?", rust.used, py_used
    );
    assert!(
        rust.available.abs_diff(py_available) <= tolerance,
        "available diverge: rust {} vs python {}", rust.available, py_available
    );
}
