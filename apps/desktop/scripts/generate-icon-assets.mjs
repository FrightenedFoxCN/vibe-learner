import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../../..");

const source = path.resolve(
  process.argv[2] ?? path.join(repoRoot, "apps/desktop/src-tauri/icons/icon-source.svg")
);
const outputDir = path.resolve(
  process.argv[3] ?? path.join(repoRoot, "apps/desktop/src-tauri/icons")
);
const tauriCli = path.join(repoRoot, "node_modules", "@tauri-apps", "cli", "tauri.js");

if (!fs.existsSync(source)) {
  throw new Error(`desktop icon source not found: ${source}`);
}

if (!fs.existsSync(tauriCli)) {
  throw new Error(`local tauri cli not found: ${tauriCli}`);
}

fs.mkdirSync(outputDir, { recursive: true });

execFileSync(process.execPath, [tauriCli, "icon", source, "-o", outputDir], {
  stdio: "inherit",
});

console.log(`generated icon assets in ${outputDir}`);
