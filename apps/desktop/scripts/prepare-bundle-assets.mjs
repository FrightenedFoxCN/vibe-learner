import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const desktopRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(desktopRoot, "../..");
const servicesAiRoot = path.join(repoRoot, "services", "ai");
const tauriRoot = path.join(desktopRoot, "src-tauri");
const generatedResourceRoot = path.join(desktopRoot, ".bundle-resources");
const sidecarBaseName = "vibe-learner-sidecar";
const requiredOcrFiles = ["detector.onnx", "recognizer.onnx", "recognizer_vocab.txt"];

main();

function main() {
  const targetTriple = resolveTargetTriple();
  const sidecarTargetPath = path.join(
    tauriRoot,
    "binaries",
    `${sidecarBaseName}-${targetTriple}${executableSuffixForTarget(targetTriple)}`
  );

  fs.mkdirSync(path.dirname(sidecarTargetPath), { recursive: true });

  buildSidecar({
    targetTriple,
    sidecarTargetPath
  });
  stageOcrModels();
}

function buildSidecar({ targetTriple, sidecarTargetPath }) {
  const buildRoot = path.join(servicesAiRoot, "build", "pyinstaller");
  const distRoot = path.join(buildRoot, "dist");
  const workRoot = path.join(buildRoot, "work");

  fs.rmSync(buildRoot, { recursive: true, force: true });
  fs.mkdirSync(distRoot, { recursive: true });
  fs.mkdirSync(workRoot, { recursive: true });

  const command = [
    "run",
    "--python",
    "3.12",
    "--with",
    "pyinstaller",
    "pyinstaller",
    "--clean",
    "--noconfirm",
    "--distpath",
    distRoot,
    "--workpath",
    workRoot,
    "pyinstaller/sidecar.spec"
  ];

  const result = spawnSync("uv", command, {
    cwd: servicesAiRoot,
    env: {
      ...process.env,
      PYTHONUTF8: "1",
      UV_CACHE_DIR: process.env.UV_CACHE_DIR || path.join(os.tmpdir(), "vibe-learner-uv-cache")
    },
    stdio: "inherit"
  });

  if (result.status !== 0) {
    throw new Error(`desktop_sidecar_pyinstaller_failed:${result.status ?? "unknown"}`);
  }

  const sidecarBinary = resolveBuiltSidecarBinary(distRoot, targetTriple);
  fs.copyFileSync(sidecarBinary, sidecarTargetPath);
  fs.chmodSync(sidecarTargetPath, 0o755);

  console.log(`Prepared desktop sidecar: ${path.relative(repoRoot, sidecarTargetPath)}`);
}

function resolveBuiltSidecarBinary(distRoot, targetTriple) {
  const executableName = `${sidecarBaseName}${executableSuffixForTarget(targetTriple)}`;
  const oneFileCandidate = path.join(distRoot, executableName);
  if (fs.existsSync(oneFileCandidate)) {
    return oneFileCandidate;
  }

  const oneDirCandidate = path.join(distRoot, sidecarBaseName, executableName);
  if (fs.existsSync(oneDirCandidate)) {
    return oneDirCandidate;
  }

  throw new Error(`desktop_sidecar_binary_missing:${oneFileCandidate}`);
}

function stageOcrModels() {
  const strictMode = process.env.VIBE_LEARNER_REQUIRE_OCR_MODELS === "1";
  const explicitSource = process.env.VIBE_LEARNER_ONNXTR_MODEL_SOURCE?.trim();
  const generatedOcrRoot = path.join(generatedResourceRoot, "ocr", "onnxtr");

  fs.rmSync(generatedResourceRoot, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(generatedOcrRoot), { recursive: true });

  const candidates = [
    explicitSource ? resolveMaybeRelative(explicitSource) : null,
    path.join(desktopRoot, "resources", "ocr", "onnxtr")
  ].filter(Boolean);

  const sourceRoot = candidates.find((candidate) => hasRequiredOcrFiles(candidate));
  if (explicitSource && !sourceRoot) {
    throw new Error(`desktop_ocr_model_source_invalid:${explicitSource}`);
  }

  if (!sourceRoot && strictMode) {
    throw new Error("desktop_ocr_model_source_missing");
  }

  const metadata = {
    included: Boolean(sourceRoot),
    preparedAt: new Date().toISOString(),
    requiredFiles: requiredOcrFiles,
    source: sourceRoot ? path.relative(repoRoot, sourceRoot) : ""
  };

  if (sourceRoot) {
    fs.cpSync(sourceRoot, generatedOcrRoot, { recursive: true });
    console.log(`Staged OCR assets from ${path.relative(repoRoot, sourceRoot)}`);
  } else {
    fs.mkdirSync(generatedOcrRoot, { recursive: true });
    console.warn("No local OnnxTR model directory found. Preview bundle will rely on runtime defaults.");
  }

  fs.writeFileSync(
    path.join(generatedOcrRoot, "manifest.json"),
    JSON.stringify(metadata, null, 2)
  );
}

function hasRequiredOcrFiles(candidate) {
  if (!candidate || !fs.existsSync(candidate)) {
    return false;
  }
  return requiredOcrFiles.every((file) => fs.existsSync(path.join(candidate, file)));
}

function resolveMaybeRelative(value) {
  return path.isAbsolute(value) ? value : path.resolve(repoRoot, value);
}

function resolveTargetTriple() {
  const explicit = process.env.VIBE_LEARNER_TARGET_TRIPLE?.trim()
    || process.env.TARGET_TRIPLE?.trim()
    || process.env.TAURI_ENV_TARGET_TRIPLE?.trim();
  if (explicit) {
    return explicit;
  }

  const platform = os.platform();
  const arch = os.arch();

  const table = {
    "darwin:arm64": "aarch64-apple-darwin",
    "darwin:x64": "x86_64-apple-darwin",
    "linux:arm64": "aarch64-unknown-linux-gnu",
    "linux:x64": "x86_64-unknown-linux-gnu",
    "win32:arm64": "aarch64-pc-windows-msvc",
    "win32:x64": "x86_64-pc-windows-msvc"
  };

  const resolved = table[`${platform}:${arch}`];
  if (!resolved) {
    throw new Error(`desktop_target_triple_unsupported:${platform}:${arch}`);
  }
  return resolved;
}

function executableSuffixForTarget(targetTriple) {
  return targetTriple.includes("windows") ? ".exe" : "";
}
