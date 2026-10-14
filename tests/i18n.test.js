"use strict";

/* Tests for the shared web translation core (web/i18n.js).
 *
 * Run with: node --test
 *
 * The `es` values are the verbatim baseline: whatever the menu, the shell or the
 * player page rendered in Spanish before this module existed must keep rendering
 * byte-for-byte the same, so a handful of the strings that carry real behaviour
 * (the sign-in rejection, the counted labels, the placeholders) are pinned here.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");

const I18n = require("../web/i18n.js");

/* A localStorage-shaped fake, so the persistence rules run without a browser. */
function fakeStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: (key) => data.delete(key),
  };
}

/* A minimal DOM good enough for apply(): a root that can answer the
 * `[data-i18n...]` selectors the core uses, plus a documentElement. */
function fakeElement(attributes = {}) {
  const attrs = new Map(Object.entries(attributes));
  return {
    textContent: "",
    getAttribute: (name) => (attrs.has(name) ? attrs.get(name) : null),
    setAttribute: (name, value) => attrs.set(name, String(value)),
    hasAttribute: (name) => attrs.has(name),
  };
}

function fakeDocument(elements) {
  const documentElement = { lang: "" };
  return {
    documentElement,
    querySelectorAll(selector) {
      const match = /^\[([a-z0-9-]+)\]$/.exec(selector);
      assert.ok(match, `apply() asked for an unexpected selector: ${selector}`);
      return elements.filter((element) => element.hasAttribute(match[1]));
    },
  };
}

test("the four languages are declared in order with their own name and an inline flag", () => {
  assert.deepEqual(
    I18n.LANGUAGES.map((language) => language.code),
    ["es", "fr", "pt", "en"],
    "the selector offers Spanish, French, Portuguese and English, in that order",
  );
  for (const language of I18n.LANGUAGES) {
    assert.ok(language.name, `${language.code} must show its own name`);
    assert.match(language.flag, /^<svg /, `${language.code} must use an inline SVG flag, never an emoji`);
  }
});

test("the default language is English", () => {
  assert.equal(I18n.DEFAULT, "en");
  assert.equal(I18n.STORAGE_KEY, "basic-engine-hub:idioma:v1");
});

test("the query string wins, then the stored choice, then the default", () => {
  const storage = fakeStorage({ [I18n.STORAGE_KEY]: "pt" });
  assert.equal(I18n.resolveLanguage("?lang=fr", storage), "fr", "?lang= beats the stored choice");
  assert.equal(I18n.resolveLanguage("", storage), "pt", "the stored choice is kept");
  assert.equal(I18n.resolveLanguage("?lang=de", storage), "pt", "an unknown ?lang= is ignored");
  assert.equal(I18n.resolveLanguage("", fakeStorage()), "en", "nothing stored falls back to English");
  assert.equal(I18n.resolveLanguage("", null), "en", "a blocked storage still resolves");
});

test("the first-visit chooser only asks while nobody has decided", () => {
  I18n.init({ storage: fakeStorage() });
  assert.equal(I18n.needsChoice(""), true, "a first visit with nothing stored must ask");

  I18n.init({ storage: fakeStorage({ [I18n.STORAGE_KEY]: "fr" }) });
  assert.equal(I18n.needsChoice(""), false, "a stored choice settles it");

  I18n.init({ storage: fakeStorage() });
  assert.equal(I18n.needsChoice("?lang=pt"), false, "an explicit ?lang= settles it too");
  assert.equal(I18n.needsChoice("?lang=de"), true, "an unknown ?lang= decides nothing");
  assert.equal(
    I18n.requestedCode("?lang=fr"),
    "fr",
    "the shell's ?lang= is read as a language, not as free text",
  );
  assert.equal(I18n.requestedCode("?lang=de"), "", "an unknown code is not a request");
  assert.equal(I18n.requestedCode(""), "", "no query string is not a request");
});

test("tr() formats the placeholders of the current language", () => {
  I18n.init({ storage: fakeStorage() });
  I18n.setLanguage("es");
  assert.equal(I18n.current(), "es");
  assert.equal(I18n.tr("loading"), "Cargando proyectos…");
  assert.equal(I18n.tr("found", { n: 3 }), "3 proyectos encontrados.");
  assert.equal(I18n.tr("filter", { visible: 2, total: 5 }), "2 de 5 proyectos encontrados.");
  assert.equal(I18n.tr("favoritesCount", { n: 4 }), "Favoritos (4)");
  assert.equal(I18n.tr("defaultTitle", { id: 42 }), "Proyecto 42");
  assert.equal(I18n.tr("sessionUser", { name: "dante" }), "Sesión de @dante en este navegador");
});

test("the Spanish sign-in rejection keeps its exact wording", () => {
  I18n.init({ storage: fakeStorage() });
  I18n.setLanguage("es");
  assert.equal(
    I18n.tr("authRejected"),
    "La confirmación no corresponde a este sitio. Se canceló el inicio de sesión.",
  );
});

test("a missing key renders its own name, so a gap is visible instead of empty", () => {
  I18n.init({ storage: fakeStorage() });
  I18n.setLanguage("es");
  assert.equal(I18n.tr("sin_esta_clave"), "sin_esta_clave");
  assert.equal(I18n.tr("found", {}), "{n} proyectos encontrados.");
});

test("setLanguage persists the choice and notifies the surfaces", () => {
  const storage = fakeStorage();
  I18n.init({ storage });
  const seen = [];
  I18n.onChange((code) => seen.push(code));
  assert.equal(I18n.setLanguage("pt"), "pt");
  assert.equal(storage.getItem(I18n.STORAGE_KEY), "pt");
  assert.deepEqual(seen, ["pt"], "listeners hear the change so the page can re-render");
});

test("an unknown language code is rejected and never persisted", () => {
  const storage = fakeStorage();
  I18n.init({ storage });
  I18n.setLanguage("es");
  assert.equal(I18n.setLanguage("de"), "en", "an unknown code falls back to the default");
  assert.equal(storage.getItem(I18n.STORAGE_KEY), "es", "the bad code must not overwrite the choice");
});

test("a fresh init picks up the stored choice", () => {
  const storage = fakeStorage({ [I18n.STORAGE_KEY]: "fr" });
  I18n.init({ storage });
  assert.equal(I18n.current(), "fr");
});

test("apply() rewrites text, attribute copy and the document language", () => {
  const storage = fakeStorage();
  I18n.init({ storage });
  I18n.setLanguage("es");
  const text = fakeElement({ "data-i18n": "refresh" });
  const label = fakeElement({ "data-i18n-aria-label": "detailCloseLabel" });
  const placeholderElement = fakeElement({ "data-i18n-placeholder": "searchPlaceholder" });
  const content = fakeElement({ "data-i18n-content": "metaDescription" });
  const title = fakeElement({ "data-i18n-title": "fsExit" });
  const page = fakeDocument([text, label, placeholderElement, content, title]);

  I18n.apply(page);

  assert.equal(text.textContent, "Actualizar");
  assert.equal(label.getAttribute("aria-label"), "Cerrar detalles");
  assert.equal(placeholderElement.getAttribute("placeholder"), "Buscar proyectos…");
  assert.match(content.getAttribute("content"), /Basic Engine Hub/);
  assert.equal(
    title.getAttribute("title"),
    "Salir de pantalla completa",
    "every attribute in ATTRIBUTES is hooked, the player page's title included",
  );
  assert.equal(page.documentElement.lang, "es", "the document language follows the choice");
});

test("every language table carries the same keys as the Spanish baseline", () => {
  const reference = Object.keys(I18n.STRINGS.es).sort();
  assert.ok(reference.length > 60, "the Spanish table is the full inventory of the web copy");
  assert.deepEqual(
    Object.keys(I18n.STRINGS).sort(),
    [...I18n.CODES].sort(),
    "the four offered languages and the tables must be the same set, so a missing table cannot pass unnoticed",
  );
  for (const [code, table] of Object.entries(I18n.STRINGS)) {
    assert.deepEqual(
      Object.keys(table).sort(),
      reference,
      `the ${code} table must cover exactly the same keys as the Spanish baseline`,
    );
    for (const [key, value] of Object.entries(table)) {
      assert.equal(typeof value, "string", `${code}.${key} must be a string`);
      assert.ok(value.length > 0, `${code}.${key} must not be empty`);
    }
  }
});

/* A coarse guard, not a translation review: it catches the easy mistake of
 * shipping a language whose table is a copy of the Spanish one. Cognates
 * ("Clones", "Variable", "Cancelar") are legitimately identical, which is why
 * the threshold is lenient rather than "every value must differ". */
test("each language is translated, not a copy of the Spanish baseline", () => {
  const reference = I18n.STRINGS.es;
  const keys = Object.keys(reference);
  for (const [code, table] of Object.entries(I18n.STRINGS)) {
    if (code === "es") continue;
    const translated = keys.filter((key) => table[key] !== reference[key]).length;
    assert.ok(
      translated >= keys.length * 0.6,
      `the ${code} table only differs from the Spanish baseline in ${translated}/${keys.length} keys`,
    );
  }
});

/* The core is a classic script loaded next to a page's own scripts, and a
 * classic script's top-level `const`/`let`/`class` lands in the scope every
 * script on that page shares. A host page redeclaring one of those names is a
 * SyntaxError at instantiation that kills the host script whole -- the menu
 * rendered no project and the player page never defined its entry point. So the
 * core owns no top-level name at all: one closure, one global. */
test("the core declares nothing in the page's shared top-level scope", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "web", "i18n.js"), "utf8");
  assert.doesNotMatch(
    source,
    /^(?:const|let|var|function|class)\s/m,
    "a top-level declaration leaks into the shared classic-script scope and can kill a host script",
  );
  assert.match(source, /^\(\(\) => \{$/m, "the helpers must stay inside one top-level closure");
});
