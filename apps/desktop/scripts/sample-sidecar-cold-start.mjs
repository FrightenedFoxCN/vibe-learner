#!/usr/bin/env node

/**
 * Samples the desktop shell's synchronous startup gate: spawned sidecar ->
 * first successful GET /health.  This deliberately mirrors the desktop
 * shell's 200ms probe cadence and does not measure WebView/window readiness.
 */
import { mkdtempSync, rmSync } from "node:fs";
import { request } from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";

const DEFAULT_SAMPLE_COUNT = 10;
const HEALTH_POLL_INTERVAL_MS = 200;
const HEALTH_REQUEST_TIMEOUT_MS = 800;
const HEALTH_TIMEOUT_MS = 20_000;

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
});

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const samples = [];

  for (let index = 0; index < options.samples; index += 1) {
    samples.push(await collectSample(index + 1, options));
  }

  const successfulDurations = samples
    .filter((sample) => sample.status === "ready")
    .map((sample) => sample.durationMs);

  const result = {
    schemaVersion: "desktop-sidecar-cold-start-v1",
    measurement: {
      boundary: "packaged_sidecar_spawn_to_first_successful_health_200",
      probeCadenceMs: HEALTH_POLL_INTERVAL_MS,
      healthRequestTimeoutMs: HEALTH_REQUEST_TIMEOUT_MS,
      overallTimeoutMs: HEALTH_TIMEOUT_MS,
      notes: [
        "Every sample uses a newly spawned packaged sidecar process and a fresh temporary SQLite/storage root.",
        "The sampler uses the desktop runtime environment and mock planning provider, and sends health probes only over loopback HTTP.",
        "This sampler does not independently prove that startup performs no outbound network request.",
        "This measures the synchronous sidecar readiness gate used during desktop startup; it excludes Tauri/WebView window readiness, frontend hydration, vault initialization/unlock, and OCR/model inference."
      ]
    },
    environment: {
      capturedAt: new Date().toISOString(),
      hostname: os.hostname(),
      platform: process.platform,
      release: os.release(),
      arch: process.arch,
      cpu: os.cpus()[0]?.model ?? "unknown",
      cpuCount: os.cpus().length,
      totalMemoryBytes: os.totalmem(),
      nodeVersion: process.version,
      binary: options.binary,
      onnxtrModelDir: options.modelDir ?? null
    },
    samples,
    summary: successfulDurations.length > 0 ? summarize(successfulDurations) : null
  };

  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  if (successfulDurations.length !== options.samples) {
    process.exitCode = 1;
  }
}

function parseArgs(argv) {
  const values = new Map();
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (!argument.startsWith("--")) {
      throw new Error(`unexpected_argument:${argument}`);
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`missing_argument_value:${argument}`);
    }
    values.set(argument, value);
    index += 1;
  }

  const binary = values.get("--binary");
  if (!binary) {
    throw new Error("missing_required_argument:--binary");
  }
  const samples = Number.parseInt(values.get("--samples") ?? String(DEFAULT_SAMPLE_COUNT), 10);
  if (!Number.isInteger(samples) || samples < 1 || samples > 100) {
    throw new Error("invalid_argument:--samples_must_be_an_integer_between_1_and_100");
  }

  return {
    binary: path.resolve(binary),
    modelDir: values.has("--model-dir") ? path.resolve(values.get("--model-dir")) : null,
    samples
  };
}

async function collectSample(index, options) {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "vibe-learner-sidecar-cold-start-"));
  let child;
  let childExit = null;
  let childError = null;
  let sidecarStderr = "";
  const startedAt = new Date().toISOString();
  const start = process.hrtime.bigint();
  let sample;

  try {
    const port = await reserveLoopbackPort();
    child = spawn(options.binary, ["--host", "127.0.0.1", "--port", String(port)], {
      stdio: ["ignore", "ignore", "pipe"],
      env: {
        ...process.env,
        DATABASE_URL: `sqlite:///${path.join(tempRoot, "vibe_learner.db")}`,
        VIBE_LEARNER_STORAGE_ROOT: tempRoot,
        VIBE_LEARNER_DESKTOP_MODE: "true",
        VIBE_LEARNER_ALLOWED_ORIGINS: "http://127.0.0.1:3000,http://localhost:3000,http://tauri.localhost,https://tauri.localhost,tauri://localhost",
        VIBE_LEARNER_OCR_ENGINE: "onnxtr",
        VIBE_LEARNER_PLAN_PROVIDER: "mock",
        ...(options.modelDir ? { VIBE_LEARNER_ONNXTR_MODEL_DIR: options.modelDir } : {})
      }
    });
    child.once("exit", (code, signal) => {
      childExit = { code, signal };
    });
    child.once("error", (error) => {
      childError = error.message;
    });
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk) => {
      sidecarStderr = `${sidecarStderr}${chunk}`.slice(-4_000);
    });

    await waitForHealth(port, start);
    sample = {
      index,
      startedAt,
      status: "ready",
      durationMs: elapsedMilliseconds(start)
    };
  } catch (error) {
    sample = {
      index,
      startedAt,
      status: "failed",
      durationMs: elapsedMilliseconds(start),
      error: error instanceof Error ? error.message : String(error)
    };
  } finally {
    await stopChild(child);
    await delay(25);
    if (sample.status === "failed") {
      if (childExit) {
        sample.sidecarExit = childExit;
      }
      if (childError) {
        sample.sidecarSpawnError = childError;
      }
      if (sidecarStderr.trim()) {
        sample.sidecarStderr = sidecarStderr.trim();
      }
    }
    rmSync(tempRoot, { recursive: true, force: true });
  }
  return sample;
}

function reserveLoopbackPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("loopback_port_allocation_failed"));
        return;
      }
      server.close((error) => (error ? reject(error) : resolve(address.port)));
    });
  });
}

async function waitForHealth(port, start) {
  const deadline = Number(start / 1_000_000n) + HEALTH_TIMEOUT_MS;
  while (elapsedMilliseconds(start) < HEALTH_TIMEOUT_MS) {
    if (await healthCheck(port)) {
      return;
    }
    await delay(HEALTH_POLL_INTERVAL_MS);
  }
  throw new Error(`health_timeout_after_ms:${Math.round(deadline - Number(start / 1_000_000n))}`);
}

function healthCheck(port) {
  return new Promise((resolve) => {
    const probe = request(
      { host: "127.0.0.1", port, path: "/health", method: "GET", timeout: HEALTH_REQUEST_TIMEOUT_MS },
      (response) => {
        response.resume();
        resolve(response.statusCode === 200);
      }
    );
    probe.once("timeout", () => probe.destroy());
    probe.once("error", () => resolve(false));
    probe.end();
  });
}

async function stopChild(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) {
    return;
  }
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    delay(2_000)
  ]);
  if (child.exitCode === null && child.signalCode === null) {
    child.kill("SIGKILL");
    await new Promise((resolve) => child.once("exit", resolve));
  }
}

function elapsedMilliseconds(start) {
  return Number(process.hrtime.bigint() - start) / 1_000_000;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function summarize(values) {
  const sorted = [...values].sort((left, right) => left - right);
  const percentile = (percent) => sorted[Math.ceil(sorted.length * percent) - 1];
  const mean = values.reduce((total, value) => total + value, 0) / values.length;
  return {
    sampleCount: values.length,
    minMs: sorted[0],
    maxMs: sorted.at(-1),
    meanMs: mean,
    p50Ms: percentile(0.5),
    p95Ms: percentile(0.95),
    percentileMethod: "nearest_rank"
  };
}
