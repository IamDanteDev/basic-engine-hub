"use strict";

/* Tests for the static shell: the two HTML entry points, the service-worker cache
 * list and the Pages workflow that ships them. They pin the drift that editing
 * only one of the two entry points would silently introduce, and they keep the
 * precache list and the CI pipeline honest.
 *
 * Run with: node --test
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..");

const i18n = require("../web/i18n.js");

function read(relative) {
  return fs.readFileSync(path.join(ROOT, relative), "utf8");
}

/* The app is served twice: from the repository root (what GitHub Pages serves)
 * and from inside web/ (what the local server serves). Both must ship the same
 * document; only the relative paths differ. Whitespace is collapsed and the
 * relative prefix of each attribute value is dropped, so the comparison fails on
 * real drift -- a control or a meta tag added to one entry point and forgotten in
 * the other -- without failing on indentation or on the path prefixes. */
function normalizeEntryPoint(html) {
  return html
    .replace(/\s+/g, " ")
    .replace(/(=")(?:\.\.\/|web\/)/g, "$1")
    .trim();
}

/* The copy inside the HTML cannot be translated by CSS, so it is both the
 * no-JavaScript fallback and the first paint. The static text and attributes in
 * the entry points must equal the Spanish baseline (whitespace collapsed, since
 * the HTML wraps a paragraph): a copy change made in the document alone, or in
 * the table alone, would otherwise show a string the site no longer means. */
function normalizeCopy(value) {
  return String(value).replace(/\s+/g, " ").trim();
}

function textHooks(html) {
  return [...html.matchAll(/<([a-z0-9]+)\b[^>]*\sdata-i18n="([^"]+)"[^>]*>([\s\S]*?)<\/\1>/gi)]
    .map((match) => ({ key: match[2], text: match[3] }));
}

/* data-i18n-<attribute> hooks: read the target attribute back out of the same
 * tag, because the HTML is free to write them in any order. */
function attributeHooks(html) {
  const hooks = [];
  for (const tag of html.matchAll(/<[a-z0-9]+[^>]*>/gi)) {
    for (const hook of tag[0].matchAll(/\bdata-i18n-([a-z-]+)="([^"]+)"/g)) {
      const attribute = hook[1];
      const found = tag[0].match(new RegExp(`(?:^|\\s)${attribute}="([^"]*)"`));
      hooks.push({ attribute, key: hook[2], value: found ? found[1] : null });
    }
  }
  return hooks;
}

test("both HTML entry points ship the same document apart from relative paths", () => {
  const root = normalizeEntryPoint(read("index.html"));
  const nested = normalizeEntryPoint(read("web/index.html"));

  assert.match(root, /id="session"/, "the shared document must mount the session chip (#session)");
  assert.match(root, /src="auth\.js" defer/, "the shared document must load the auth core");

  assert.equal(nested, root, "web/index.html drifted from index.html");
});

/* Classic scripts on one page share a single top-level scope, so two of them
 * declaring the same `const`/`let`/`class` name is a SyntaxError that kills the
 * second script whole: the menu then never renders a project (the page "does not
 * load the projects") and the player page loses the `loadScratchProjectBytes`
 * hook the shell calls. Compiling a page's scripts as one source reproduces the
 * browser's check exactly, because only the compile step sees that shared scope
 * -- running each file on its own, or a per-file syntax check, never does. */
function pageScripts(page, pageDir) {
  const sources = [];
  for (const script of read(page).matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
    const src = (script[1].match(/\bsrc="([^"]+)"/) || [])[1];
    if (!src) {
      sources.push({ name: `${page} inline script`, source: script[2] });
      continue;
    }
    if (/^[a-z][a-z0-9+.-]*:|^\/\//i.test(src)) continue; /* a CDN script is not ours to read */
    const file = path.join(pageDir, src);
    assert.ok(fs.existsSync(file), `${page} loads "${src}", which does not exist`);
    sources.push({ name: src, source: fs.readFileSync(file, "utf8") });
  }
  return sources;
}

test("the classic scripts of each page can share one top-level scope", () => {
  for (const [page, pageDir] of [
    ["index.html", ROOT],
    ["web/index.html", path.join(ROOT, "web")],
    ["web/player.html", path.join(ROOT, "web")],
  ]) {
    const scripts = pageScripts(page, pageDir);
    assert.ok(scripts.length >= 2, `${page} must load more than one classic script`);
    const combined = scripts.map((script) => script.source).join("\n;\n");
    try {
      new vm.Script(combined, { filename: page });
    } catch (error) {
      assert.fail(
        `${page}: ${scripts.map((script) => script.name).join(" + ")} cannot share one top-level scope: ${error.message}`,
      );
    }
  }
});

test("every service-worker shell path exists in the repository", () => {
  const declared = read("sw.js").match(/const SHELL_PATHS = \[([\s\S]*?)\]/);
  assert.ok(declared, "sw.js must declare SHELL_PATHS");

  const paths = [...declared[1].matchAll(/"([^"]+)"/g)].map((match) => match[1]);
  assert.ok(paths.length >= 6, "SHELL_PATHS must cover the shipped shell");
  assert.ok(paths.includes("./web/auth.js"), "the shell must precache the auth core");

  for (const entry of paths) {
    const relative = entry === "./" ? "index.html" : entry.replace(/^\.\//, "");
    assert.ok(
      fs.existsSync(path.join(ROOT, relative)),
      `SHELL_PATHS lists ${entry}, but ${relative} is not in the repository`,
    );
  }
});

test("the Pages workflow runs both suites before uploading the artifact", () => {
  const workflow = read(".github/workflows/pages.yml");
  const upload = workflow.indexOf("upload-pages-artifact");
  const python = workflow.indexOf("python -m unittest");
  const node = workflow.indexOf("node --test");

  assert.ok(upload > 0, "the workflow must upload the Pages artifact");
  assert.ok(python > 0, "the workflow must run the Python tests");
  assert.ok(node > 0, "the workflow must run the Node tests");
  assert.ok(python < upload, "the Python tests must run before the artifact is uploaded");
  assert.ok(node < upload, "the Node tests must run before the artifact is uploaded");
});

test("the workflow installs the Python dependencies the suite imports", () => {
  const workflow = read(".github/workflows/pages.yml");
  const requirements = read("requirements.txt");

  assert.match(requirements, /^requests/m, "requirements.txt must list requests");
  assert.match(requirements, /^beautifulsoup4/m, "requirements.txt must list beautifulsoup4");
  assert.match(
    workflow,
    /pip install [^\n]*(requirements\.txt|requests|beautifulsoup4)/,
    "the suite imports web.serve, which imports hub.scratch_api, which imports requests and bs4: the workflow must install them",
  );
});

test("both entry points load the i18n core before the menu script", () => {
  for (const file of ["index.html", "web/index.html"]) {
    const html = read(file);
    assert.match(
      html,
      /<script src="(?:web\/)?i18n\.js" defer><\/script>/,
      `${file} must load the shared translation core`,
    );
    assert.ok(
      html.indexOf("i18n.js") < html.indexOf("app.js"),
      `${file} must load the core before app.js, which reads it at first render`,
    );
  }
});

test("every data-i18n hook in the entry points names a key of the Spanish baseline", () => {
  for (const file of ["index.html", "web/index.html"]) {
    const html = read(file);
    const used = [...html.matchAll(/\bdata-i18n(?:-[a-z-]+)?="([^"]+)"/g)].map((match) => match[1]);
    assert.ok(used.length >= 40, `${file} must hook the whole shell, found ${used.length}`);
    for (const key of used) {
      assert.ok(
        Object.prototype.hasOwnProperty.call(i18n.STRINGS.es, key),
        `${file} hooks "${key}", which the es table does not carry`,
      );
    }
  }
});

test("the static text in the entry points matches the Spanish baseline", () => {
  for (const file of ["index.html", "web/index.html"]) {
    const hooks = textHooks(read(file));
    assert.ok(hooks.length >= 20, `${file} must hook its static text, found ${hooks.length}`);
    for (const { key, text } of hooks) {
      assert.equal(
        normalizeCopy(text),
        normalizeCopy(i18n.STRINGS.es[key]),
        `${file}: the fallback text for "${key}" drifted from the es table`,
      );
    }
  }
});

test("the static attribute copy in the entry points matches the Spanish baseline", () => {
  for (const file of ["index.html", "web/index.html"]) {
    const hooks = attributeHooks(read(file));
    assert.ok(hooks.length >= 8, `${file} must hook its attribute copy, found ${hooks.length}`);
    for (const { attribute, key, value } of hooks) {
      assert.equal(
        normalizeCopy(value),
        normalizeCopy(i18n.STRINGS.es[key]),
        `${file}: the ${attribute} fallback for "${key}" drifted from the es table`,
      );
    }
  }
});

test("the menu script only asks for keys the tables carry", () => {
  const app = read("web/app.js");
  const keys = new Set();
  for (const call of app.matchAll(/(?<![A-Za-z0-9_])tr\(([^()]*)\)/g)) {
    for (const literal of call[1].matchAll(/"([A-Za-z0-9]+)"/g)) keys.add(literal[1]);
  }
  assert.ok(keys.size >= 30, `the menu must resolve its copy through tr(), found ${keys.size} keys`);
  for (const key of keys) {
    assert.ok(
      Object.prototype.hasOwnProperty.call(i18n.STRINGS.es, key),
      `web/app.js asks for "${key}", which the es table does not carry`,
    );
  }
});

/* The menu script looks its controls up by id, in the document that ships in
 * two copies: a typo in either file is a runtime crash, not a compile error. */
test("every control the menu script looks up exists in the entry point", () => {
  const app = read("web/app.js");
  const html = read("index.html");
  const ids = [...new Set([...app.matchAll(/getElementById\("([^"]+)"\)/g)].map((match) => match[1]))];
  assert.ok(ids.length >= 40, `the menu looks up ${ids.length} ids`);
  for (const id of ids) {
    assert.ok(html.includes(`id="${id}"`), `web/app.js looks up #${id}, which index.html does not mount`);
  }
});

/* The player page is the third web surface and the desktop shell's bridge. It
 * used to carry a private two-language table (so a French or Portuguese app
 * showed a Spanish or English player); it now asks the shared core. The risks
 * that remain are a renamed key, a missing script and the old table creeping
 * back. */
test("the player page asks the shared core instead of carrying its own table", () => {
  const html = read("web/player.html");
  assert.match(html, /<script src="i18n\.js"><\/script>/, "the core must be loaded");
  assert.ok(
    html.indexOf('src="i18n.js"') < html.indexOf('"use strict"'),
    "the core must be loaded before the page's own script runs",
  );
  assert.ok(!/const UI = \{/.test(html), "the player page must not carry its own table");
  assert.ok(!/uiText\(/.test(html), "the player page must resolve its copy through the core");
  assert.match(
    html,
    /window\.setPlayerLanguage = function \(lang\) \{\s*if \(typeof I18n === "undefined" \|\| !I18n\.isKnownCode\(lang\)\) return;\s*I18n\.setLanguage\(lang\);/,
    "the shell's live switch must delegate to the core",
  );
});

test("every key the player page asks for names a key of the Spanish baseline", () => {
  const html = read("web/player.html");
  const keys = new Set();
  for (const call of html.matchAll(/(?<![A-Za-z0-9_])tr\("([A-Za-z0-9]+)"\)/g)) keys.add(call[1]);
  assert.ok(keys.size >= 5, `the player must resolve its copy through the core, found ${keys.size} keys`);
  for (const key of keys) {
    assert.ok(
      Object.prototype.hasOwnProperty.call(i18n.STRINGS.es, key),
      `web/player.html asks for "${key}", which the es table does not carry`,
    );
  }
});

test("the player page's static copy matches the Spanish baseline", () => {
  const hooks = attributeHooks(read("web/player.html"));
  assert.ok(hooks.length >= 2, `the player must hook its static copy, found ${hooks.length}`);
  for (const { attribute, key, value } of hooks) {
    assert.equal(
      normalizeCopy(value),
      normalizeCopy(i18n.STRINGS.es[key]),
      `web/player.html: the ${attribute} fallback for "${key}" drifted from the es table`,
    );
  }
});

test("the app and the web offer the same language codes", () => {
  // The desktop shell hands the player page its language as ?lang=<code>, with
  // hub/i18n.current() on one side and this table on the other: a code the app
  // offers but the core does not know would silently play in the default, and a
  // code the core offers but the app does not would be unreachable from the app.
  const python = read("hub/i18n.py").match(/^LANGUAGES = \{([^}]*)\}/m);
  assert.ok(python, "hub/i18n.py must declare LANGUAGES on one line");
  const appCodes = [...python[1].matchAll(/"([a-z]{2})":/g)].map((match) => match[1]);
  assert.deepEqual(
    appCodes,
    [...i18n.CODES],
    "the app's language list and the web core's list must be the same codes in the same order",
  );
});

test("both entry points offer the header selector and the first-visit chooser", () => {
  for (const file of ["index.html", "web/index.html"]) {
    const html = read(file);
    assert.match(
      html,
      /<select id="language" class="language-select"[^>]*data-i18n-aria-label="languageLabel"><\/select>/,
      `${file} must offer the compact selector, labelled like every other control`,
    );
    assert.match(
      html,
      /<dialog id="language-chooser" class="language-chooser" aria-labelledby="language-chooser-title">/,
      `${file} must offer the first-visit chooser`,
    );
    assert.match(
      html,
      /<div id="language-chooser-options" class="language-chooser-options"><\/div>/,
      `${file} must leave the chooser's four options to the script, so they cannot drift from the table`,
    );
  }
});

/* The chooser and the select are built by the menu script from the core's list;
 * if either were written by hand in the HTML the flags would be duplicated. */
test("the menu script builds the selector from the core's list", () => {
  const app = read("web/app.js");
  assert.match(app, /for \(const language of i18n\.LANGUAGES\)/, "the options come from the core");
  assert.match(app, /language\.flag/, "the chooser shows the inline SVG flag");
  assert.match(
    app,
    /if \(i18n && i18n\.needsChoice\(window\.location\.search\)\)/,
    "the chooser shows only while nobody has chosen a language",
  );
});

/* Each language is offered as its own title art, declared twice: a filename per
 * code in hub/i18n.py for the desktop shell and a `title` per language in the web
 * core. A rename on one side would leave the other offering a broken image. */
test("the app and the web name the same title image for every language", () => {
  const python = read("hub/i18n.py").match(/^TITLE_FILES = \{([^}]*)\}/m);
  assert.ok(python, "hub/i18n.py must declare TITLE_FILES on one line");
  const appTitles = [...python[1].matchAll(/"([a-z]{2})": "([^"]+)"/g)].map((match) => [
    match[1],
    match[2],
  ]);
  assert.deepEqual(
    appTitles,
    i18n.LANGUAGES.map((language) => [language.code, language.title]),
    "both surfaces must show the same title art for the same language",
  );
});

test("the chooser shows each language as its own title art", () => {
  const app = read("web/app.js");
  assert.match(
    app,
    /assetUrl\(`Lengs\/Titles\/\$\{language\.title\}`\)/,
    "the chooser builds the title URL from the core's list, under the shared Assets/",
  );
  assert.match(
    app,
    /title\.alt = language\.name/,
    "the image keeps the plain language name as its alt text",
  );
});
