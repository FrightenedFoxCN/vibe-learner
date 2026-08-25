import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const topNavSource = readFileSync(
  new URL("../components/top-nav.tsx", import.meta.url),
  "utf8",
);
const studyConsoleSource = readFileSync(
  new URL("../components/study-console.tsx", import.meta.url),
  "utf8",
);
const globalStyles = readFileSync(
  new URL("../app/globals.css", import.meta.url),
  "utf8",
);
const providerTruthSource = readFileSync(
  new URL("../components/provider-truth.tsx", import.meta.url),
  "utf8",
);

test("mobile primary navigation keeps labelled 44px touch targets", () => {
  assert.match(topNavSource, /aria-label=\{item\.label\}/);
  assert.match(topNavSource, /className="app-nav-label"/);
  assert.match(
    globalStyles,
    /@media \(max-width: 760px\)[\s\S]*?\.app-nav-link,[\s\S]*?flex: 0 0 44px;[\s\S]*?min-width: 44px;[\s\S]*?justify-content: center;/,
  );
});

test("Study question composer exposes an accessible name", () => {
  assert.match(
    studyConsoleSource,
    /<textarea[\s\S]*?aria-label=\{`向\$\{persona\.name\}提问`\}[\s\S]*?placeholder="输入本节学习问题…"/,
  );
});

test("Tavern mobile controls keep 44px touch targets", () => {
  assert.match(
    globalStyles,
    /\.tavern-load-older \{[\s\S]*?min-width: 44px;[\s\S]*?min-height: 44px;/,
  );
  assert.match(
    globalStyles,
    /@media \(max-width: 480px\)[\s\S]*?\.tavern-setup-form input,[\s\S]*?\.tavern-setup-form select \{[\s\S]*?height: 44px;[\s\S]*?min-height: 44px;/,
  );
  assert.match(providerTruthSource, /summary: \{[\s\S]*?minHeight: 44,/);
});
