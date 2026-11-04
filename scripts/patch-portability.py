#!/usr/bin/env python3
"""Fail-closed source-level portable data patch for the *temporary* Pake clone.

Based on verified Pake V3.18.0 src-tauri/src/util.rs and lib.rs. Rejects a
changed upstream layout rather than shipping a normal nonportable WebView2 app.
"""
from pathlib import Path
import re
import sys

# Tauri's appDirectoriesOverride controls window-state and plugin app directories.
# Pake separately calls WebviewWindowBuilder::data_directory with get_data_dir().
# That call needs its own patch; changing APPDATA alone is insufficient.
CONTEXT_PATCH = '''let mut context = tauri::generate_context!();
    // Portable source adaptation: Tauri application and plugin data belong to
    // the app's own Data directory, including after moving between drives.
    #[cfg(target_os = "windows")]
    {
        let exe = std::env::current_exe().expect("PakePortable: cannot find executable");
        let root = exe.parent().expect("PakePortable: cannot find executable directory");
        context.config_mut().app.app_directories_override = Some(
            tauri::utils::config::AppDirectoriesOverride::Root(
                root.join("Data").join("State")
            )
        );
    }'''

WINDOW_DATA_PATCH = '''pub fn get_data_dir(app: &AppHandle, package_name: String) -> std::io::Result<PathBuf> {
    #[cfg(target_os = "windows")]
    let data_dir = {
        // PakePortable R6: controlled per-app WebView2 profile; never relocate
        // existing host profiles or write into a shared LocalAppData directory.
        let executable = std::env::current_exe()?;
        let root = executable.parent().ok_or_else(||
            std::io::Error::other("PakePortableR6: executable directory not found"))?;
        root.join("Data").join("WebView").join(package_name)
    };
    #[cfg(not(target_os = "windows"))]
    let data_dir = app.path().config_dir().map_err(|err|
        std::io::Error::new(std::io::ErrorKind::NotFound, err.to_string()))?.join(package_name);
    std::fs::create_dir_all(&data_dir)?;
    Ok(data_dir)
}
'''


def patch_files(root: Path):
    libpath = root / "src-tauri/src/lib.rs"
    utilpath = root / "src-tauri/src/util.rs"
    lib = libpath.read_text(encoding="utf-8")
    util = utilpath.read_text(encoding="utf-8")
    anchor = "let mut context = tauri::generate_context!();"
    if lib.count(anchor) != 1 or "PakePortable: cannot find executable" in lib:
        raise RuntimeError("Upstream lib.rs context layout changed; portable path override not applied")
    lib = lib.replace(anchor, CONTEXT_PATCH, 1)
    pattern = re.compile(r"pub fn get_data_dir\(app: &AppHandle, package_name: String\) -> std::io::Result<PathBuf>\s*\{.*?\n\}\s*(?=pub fn read_last_url\()", re.S)
    if len(pattern.findall(util)) != 1 or "PakePortableR6" in util:
        raise RuntimeError("Upstream util.rs WebView data layout changed; refusing nonportable build")
    util = pattern.sub(WINDOW_DATA_PATCH + "\n", util, count=1)
    if "root.join(\"Data\").join(\"WebView\")" not in util:
        raise RuntimeError("WebView2 profile redirection patch verification failed")
    if "app_directories_override" not in lib:
        raise RuntimeError("Tauri state path patch verification failed")
    libpath.write_text(lib, encoding="utf-8", newline="\n")
    utilpath.write_text(util, encoding="utf-8", newline="\n")
    print("Applied two source-level patches: WebView2 directory and Tauri application/plugin paths.")
    print("No host profile directories will be moved or deleted by this build.")


if __name__ == "__main__":
    patch_files(Path(sys.argv[1] if len(sys.argv) > 1 else "work/upstream"))
