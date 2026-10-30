import fs from "node:fs/promises";
import http from "node:http";
import https from "node:https";
import path from "node:path";
import { fileURLToPath } from "node:url";
import zlib from "node:zlib";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const ROUTES = ["/", "/settings", "/model-usage", "/tavern"];
const REGRESSION_LIMIT = 0.05;

const options = parseArgs(process.argv.slice(2));
const report = await measure(options.baseUrl);

if (options.output) {
  await fs.writeFile(options.output, `${JSON.stringify(report, null, 2)}\n`);
}

for (const route of report.routes) {
  console.log(
    `${route.route} html=${route.html_gzip_bytes} assets=${route.asset_gzip_bytes} total=${route.total_gzip_bytes}`,
  );
}

if (options.baseline) {
  const baseline = JSON.parse(await fs.readFile(options.baseline, "utf8"));
  const failures = compareBaseline(report, baseline);
  if (failures.length) {
    for (const failure of failures) console.error(`::error::${failure}`);
    process.exitCode = 1;
  }
}

function parseArgs(args) {
  const parsed = {
    baseUrl: process.env.WEB_BUNDLE_BASE_URL ?? "http://127.0.0.1:13417",
    baseline: "",
    output: "",
  };
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--base-url") parsed.baseUrl = args[++index];
    else if (arg === "--baseline") parsed.baseline = args[++index];
    else if (arg === "--output") parsed.output = args[++index];
    else throw new Error(`unknown argument: ${arg}`);
  }
  return parsed;
}

async function measure(baseUrl) {
  const origin = new URL(baseUrl);
  const buildId = await readBuildId();
  const routes = [];

  for (const route of ROUTES) {
    const page = await request(origin, route);
    const html = decodeBody(page.body, page.headers["content-encoding"]);
    const assets = extractAssets(html, origin);
    const assetReports = [];

    for (const asset of assets) {
      const response = await request(origin, asset);
      assetReports.push({
        path: asset,
        status: response.status,
        gzip_bytes: response.body.length,
        encoding: response.headers["content-encoding"] ?? "identity",
      });
    }

    routes.push({
      route,
      status: page.status,
      html_gzip_bytes: page.body.length,
      html_encoding: page.headers["content-encoding"] ?? "identity",
      asset_count: assetReports.length,
      asset_gzip_bytes: assetReports.reduce((sum, asset) => sum + asset.gzip_bytes, 0),
      total_gzip_bytes:
        page.body.length +
        assetReports.reduce((sum, asset) => sum + asset.gzip_bytes, 0),
      assets: assetReports,
    });
  }

  return {
    schema_version: "web-bundle-baseline-v1",
    measured_at: new Date().toISOString(),
    base_url: origin.origin,
    build_id: buildId,
    routes,
  };
}

function request(origin, pathname) {
  return new Promise((resolve, reject) => {
    const url = new URL(pathname, origin);
    const transport = url.protocol === "https:" ? https : http;
    const requestOptions = {
      hostname: url.hostname,
      port: url.port,
      path: `${url.pathname}${url.search}`,
      headers: {
        "accept-encoding": "gzip",
        accept: "text/html, text/css, application/javascript",
      },
    };
    const request = transport.get(requestOptions, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        resolve({
          status: response.statusCode ?? 0,
          headers: Object.fromEntries(
            Object.entries(response.headers).map(([key, value]) => [
              key,
              Array.isArray(value) ? value.join(",") : (value ?? ""),
            ]),
          ),
          body: Buffer.concat(chunks),
        });
      });
    });
    request.on("error", reject);
  });
}

function decodeBody(body, encoding) {
  if (encoding?.includes("gzip")) return zlib.gunzipSync(body).toString("utf8");
  return body.toString("utf8");
}

function extractAssets(html, origin) {
  const paths = new Set();
  const attributePattern = /(?:src|href)=["']([^"']+)["']/gu;
  for (const match of html.matchAll(attributePattern)) {
    const url = new URL(match[1], origin);
    if (url.origin !== origin.origin || !url.pathname.startsWith("/_next/static/"))
      continue;
    if (!/\.(?:js|css)$/u.test(url.pathname)) continue;
    paths.add(url.pathname);
  }
  return [...paths].sort();
}

async function readBuildId() {
  return (await fs.readFile(path.join(ROOT, "apps/web/.next/BUILD_ID"), "utf8")).trim();
}

function compareBaseline(report, baseline) {
  const expected = new Map(baseline.routes.map((route) => [route.route, route]));
  const failures = [];
  for (const route of report.routes) {
    const previous = expected.get(route.route);
    if (!previous) {
      failures.push(`${route.route}: route is missing from baseline`);
      continue;
    }
    const limit = Math.ceil(previous.total_gzip_bytes * (1 + REGRESSION_LIMIT));
    if (route.total_gzip_bytes > limit) {
      failures.push(
        `${route.route}: ${route.total_gzip_bytes} gzip bytes exceeds ${limit} (${REGRESSION_LIMIT * 100}% over baseline ${previous.total_gzip_bytes})`,
      );
    }
  }
  return failures;
}
