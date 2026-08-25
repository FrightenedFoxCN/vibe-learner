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
const tavernWorkspaceSource = readFileSync(
  new URL("../components/tavern-workspace.tsx", import.meta.url),
  "utf8",
);
const settingsSectionsSource = readFileSync(
  new URL("../components/settings/settings-sections.tsx", import.meta.url),
  "utf8",
);
const settingsStylesSource = readFileSync(
  new URL("../components/settings/settings-styles.ts", import.meta.url),
  "utf8",
);
const personaSpectrumSource = readFileSync(
  new URL("../app/persona-spectrum/page.tsx", import.meta.url),
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

test("Tavern mobile controls keep 44px touch targets and provider state is announced", () => {
  assert.match(
    globalStyles,
    /\.tavern-load-older \{[\s\S]*?min-width: 44px;[\s\S]*?min-height: 44px;/,
  );
  assert.match(
    globalStyles,
    /@media \(max-width: 480px\)[\s\S]*?\.tavern-setup-form input,[\s\S]*?\.tavern-setup-form select \{[\s\S]*?height: 44px;[\s\S]*?min-height: 44px;/,
  );
  assert.match(providerTruthSource, /role="status"/);
  assert.match(providerTruthSource, /aria-label=\{description\}/);
});

test("Tavern sequence updates are announced without appearing in the transcript", () => {
  assert.match(tavernWorkspaceSource, /<p className="sr-only" aria-live="polite">[\s\S]*?最新消息序号/);
  assert.match(globalStyles, /\.sr-only \{[\s\S]*?clip: rect\(0, 0, 0, 0\);/);
});

test("model scope connection fields stay compact and new personas begin as drafts", () => {
  assert.match(settingsSectionsSource, /<label style=\{styles\.compactConnectionField\}>[\s\S]*?<span style=\{styles\.label\}>访问密钥/);
  assert.match(settingsSectionsSource, /<label style=\{styles\.compactConnectionField\}>[\s\S]*?<span style=\{styles\.label\}>服务地址/);
  assert.match(settingsStylesSource, /compactConnectionField:[\s\S]*?maxWidth: 280/);
  assert.match(personaSpectrumSource, /function handleNewPersonaDraft\(\)/);
  assert.match(personaSpectrumSource, /onClick=\{handleNewPersonaDraft\}/);
  assert.match(personaSpectrumSource, /selectedPersonaId \? handleUpdatePersona\(\) : handleCreatePersona\(\)/);
  assert.match(personaSpectrumSource, /<option value="">新建人格（未保存）<\/option>/);
});
