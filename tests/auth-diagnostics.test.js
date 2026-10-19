"use strict";
/* Regression probes for the Scratch sign-in console diagnostics in web/app.js.
 * A1 the fetch wrapper keeps fetch semantics (same response, same rejection);
 * A2 the privateCode is redacted before any url reaches the console;
 * A4 the first pending poll logs, then every AUTH_POLL_LOG_EVERY-th.
 * The functions are read out of the real file (this repo has no jsdom harness
 * on purpose), so the assertions run the shipped source, not a copy of it. */
const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const APP = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
const SIGN_IN_START = APP.indexOf("function redactAuthUrl");
const SIGN_IN_END = APP.indexOf("function renderSession");

function loadDiagnostics(fetchStub, reportStub) {
  assert.ok(SIGN_IN_START > 0 && SIGN_IN_END > SIGN_IN_START, "web/app.js no longer carries the sign-in diagnostics block");
  const src = APP.slice(SIGN_IN_START, SIGN_IN_END);
  const factory = new Function("fetch", "report",
    "let authHttpStatus = 0;\n" + src + "\nreturn { redactAuthUrl, fetchImpl, status: () => authHttpStatus };");
  return factory(fetchStub, reportStub);
}

function reportCalls(source) {
  const calls = [];
  const re = /\breport\(/g;
  let match;
  while ((match = re.exec(source))) {
    let depth = 0;
    let text = "";
    for (let i = match.index + "report".length; i < source.length; i++) {
      const char = source[i];
      text += char;
      if (char === "(") depth++;
      else if (char === ")") { depth--; if (depth === 0) break; }
    }
    calls.push({ line: source.slice(0, match.index).split("\n").length, text });
  }
  return calls;
}

/* The service issues a long hex privateCode; that is the shape to redact. */
const PRIVATE = "9f1c47b0de5a2c8831aa6d0f4b7e29c5a03f18d6e7b4c9208da51f36be70c4a9";
const POLL = `https://auth-api.itinerary.eu.org/auth/verifyToken/${PRIVATE}`;
const TOKENS = "https://auth-api.itinerary.eu.org/auth/getTokens?method=cloud&redirect=aHR0cHM6Ly9leGFtcGxlLmNvbQ%3D%3D&authProject=1391621033";

test("the session wrapper resolves with the same response and rejects with the same reason", async () => {
  const response = { ok: true, status: 200 };
  const seen = [];
  const wrap = loadDiagnostics((url) => { seen.push(url); return Promise.resolve(response); }, () => {});
  const returned = await wrap.fetchImpl(TOKENS);
  assert.equal(returned, response, "fetchImpl must hand the caller the response object fetch resolved with");
  assert.deepEqual(seen, [TOKENS], "fetchImpl must call fetch once, with the url it was given");

  const failure = Object.assign(new TypeError("Failed to fetch"), { marker: "original" });
  const failing = loadDiagnostics(() => Promise.reject(failure), () => {});
  await assert.rejects(() => failing.fetchImpl(POLL), (error) => error === failure, "the rejection reason must survive unchanged");
});

test("the privateCode is redacted in the url the console can see", () => {
  const wrap = loadDiagnostics(() => Promise.resolve({ ok: true, status: 200 }), () => {});
  const redacted = wrap.redactAuthUrl(POLL);
  assert.ok(!redacted.includes(PRIVATE), "the privateCode must not survive redaction");
  assert.equal(redacted, "https://auth-api.itinerary.eu.org/auth/verifyToken/<privateCode>");
  assert.equal(wrap.redactAuthUrl(`${POLL}?a=1&b=2`), "https://auth-api.itinerary.eu.org/auth/verifyToken/<privateCode>?a=1&b=2");
  assert.equal(wrap.redactAuthUrl(TOKENS), TOKENS, "a url without a privateCode must be logged untouched");
});

test("no report call anywhere in web/app.js can print the privateCode", () => {
  const calls = reportCalls(APP);
  assert.ok(calls.length >= 30, `expected the file to carry its diagnostics, found ${calls.length}`);
  const leaks = calls.filter((call) => /privateCode/.test(call.text));
  assert.deepEqual(leaks.map((call) => call.line), [], "a report call carries the privateCode");
});

test("a poll response only records the status; pollSignIn owns the summary line", async () => {
  const logged = [];
  const wrap = loadDiagnostics(() => Promise.resolve({ ok: false, status: 403 }), (...args) => logged.push(args));
  const response = await wrap.fetchImpl(POLL);
  assert.equal(response.status, 403);
  assert.equal(wrap.status(), 403, "the poll status must be kept for the summary line");
  assert.deepEqual(logged, [], "a poll must not log on its own: that would be one line every 3 seconds");
});

test("the first pending poll logs, then every fifth", () => {
  const every = Number((APP.match(/AUTH_POLL_LOG_EVERY\s*=\s*(\d+)/) || [])[1]);
  assert.equal(every, 5, "one pending summary every five polls");
  assert.match(APP, /authState\.attempts % AUTH_POLL_LOG_EVERY === 1/, "the first poll (attempt 1) must log");
  assert.equal(1 % every, 1, "attempt 1 falls on the logged slot");
  assert.equal(Number((APP.match(/AUTH_POLL_MS\s*=\s*(\d+)/) || [])[1]), 3000);
});
