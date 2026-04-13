use std::path::PathBuf;
use std::process::Command;

fn main() {
    println!("cargo:rerun-if-changed=icons/icon-source.svg");
    println!("cargo:rerun-if-changed=../scripts/generate-icon-assets.mjs");

    generate_desktop_icon();
    tauri_build::build()
}

fn generate_desktop_icon() {
    let manifest_dir = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").expect("missing CARGO_MANIFEST_DIR"));
    let icons_dir = manifest_dir.join("icons");
    let source_svg = icons_dir.join("icon-source.svg");
    let generator_script = manifest_dir
        .parent()
        .expect("src-tauri should have parent")
        .join("scripts")
        .join("generate-icon-assets.mjs");

    if !generator_script.exists() {
        panic!(
            "desktop icon generator not found: {}",
            generator_script.display()
        );
    }

    if !source_svg.exists() {
        panic!("desktop icon source not found: {}", source_svg.display());
    }

    let status = Command::new("node")
        .arg(generator_script.to_str().expect("invalid script path"))
        .arg(source_svg.to_str().expect("invalid svg path"))
        .arg(icons_dir.to_str().expect("invalid icons dir"))
        .status()
        .expect("failed to execute desktop icon generator");

    if !status.success() {
        panic!(
            "failed to generate desktop icon assets in {}",
            icons_dir.display()
        );
    }
}
