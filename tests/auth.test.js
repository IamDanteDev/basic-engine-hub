"use strict";

/* Tests for the Scratch sign-in core (web/auth.js).
 *
 * Run with: node --test tests/
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const Auth = require("../web/auth.js");

/* A localStorage-shaped fake, so the session rules can be checked without a browser. */
function fakeStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: (key) => data.delete(key),
  };
}

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

test("auth constants match the chosen Scratch Auth project", () => {
  assert.equal(Auth.AUTH_API_BASE, "https://auth-api.itinerary.eu.org");
  assert.equal(Auth.AUTH_PROJECT_ID, 1391621033);
  assert.equal(Auth.AUTH_PROJECT_URL, "https://scratch.mit.edu/projects/1391621033/");
  assert.deepEqual(Auth.AUTH_METHODS, ["cloud", "comment", "profile-comment"]);
  assert.equal(Auth.isKnownMethod("cloud"), true);
  assert.equal(Auth.isKnownMethod("profile-comment"), true);
  assert.equal(Auth.isKnownMethod("telepathy"), false);
});

test("buildCallbackUrl uses origin plus path and drops the trailing slash", () => {
  assert.equal(Auth.buildCallbackUrl({ origin: "http://localhost:8000", pathname: "/" }), "http://localhost:8000");
  assert.equal(
    Auth.buildCallbackUrl({ origin: "https://iamdantedev.github.io", pathname: "/basic-engine-hub/web/" }),
    "https://iamdantedev.github.io/basic-engine-hub/web",
  );
});

test("buildTokensUrl percent-encodes the base64 redirect", () => {
  const url = Auth.buildTokensUrl({
    redirect: "http://localhost:8000",
    method: "cloud",
    authProject: 1391621033,
  });
  const parsed = new URL(url);

  assert.equal(parsed.origin, "https://auth-api.itinerary.eu.org");
  assert.equal(parsed.pathname, "/auth/getTokens");
  assert.equal(parsed.searchParams.get("method"), "cloud");
  assert.equal(parsed.searchParams.get("authProject"), "1391621033");
  assert.equal(Auth.base64Decode(parsed.searchParams.get("redirect")), "http://localhost:8000");
});

test("buildTokensUrl survives a base64 redirect that contains a plus sign", () => {
  /* Evidence L6: sending raw base64 corrupts the redirect, because a bare "+"
   * in a query string decodes as a space (https://example.com/x>>> came back
   * as https://example.com/x>>). The encoding must therefore be percent-safe. */
  const redirect = "https://example.com/x>>>";
  const encoded = Auth.encodeRedirect(redirect);
  assert.ok(encoded.includes("+"), "the fixture must contain a + to be meaningful");

  const url = Auth.buildTokensUrl({ redirect, method: "cloud", authProject: 1391621033 });
  const rawQuery = url.slice(url.indexOf("?") + 1);

  assert.equal(rawQuery.includes("+"), false, "the query must not carry a bare +");
  assert.equal(Auth.base64Decode(new URL(url).searchParams.get("redirect")), redirect);
});

test("buildTokensUrl sends the username only for the profile-comment method", () => {
  const cloud = new URL(Auth.buildTokensUrl({ redirect: "http://x/", method: "cloud", authProject: 1, username: "alguien" }));
  assert.equal(cloud.searchParams.get("username"), null);

  const profile = new URL(
    Auth.buildTokensUrl({ redirect: "http://x/", method: "profile-comment", authProject: 1, username: "alguien" }),
  );
  assert.equal(profile.searchParams.get("username"), "alguien");
  assert.equal(profile.searchParams.get("method"), "profile-comment");
});

test("verifyUrl targets the private code endpoint", () => {
  assert.equal(
    Auth.verifyUrl({ privateCode: "abc123" }),
    "https://auth-api.itinerary.eu.org/auth/verifyToken/abc123",
  );
});

test("isTrustedRedirect accepts our own callback and rejects another site", () => {
  const expected = "https://iamdantedev.github.io/basic-engine-hub/web";

  assert.equal(Auth.isTrustedRedirect(expected, expected), true);
  assert.equal(Auth.isTrustedRedirect(`${expected}/`, expected), true);
  assert.equal(Auth.isTrustedRedirect(Auth.encodeRedirect(expected), expected), true);
  assert.equal(Auth.isTrustedRedirect("https://evil.example/", expected), false);
  assert.equal(Auth.isTrustedRedirect("https://iamdantedev.github.io/basic-engine-hub/other.html", expected), false);
  assert.equal(Auth.isTrustedRedirect("http://iamdantedev.github.io/basic-engine-hub/web", expected), false);
});

test("isTrustedRedirect tolerates a trailing slash difference on localhost", () => {
  assert.equal(Auth.isTrustedRedirect("http://localhost:8000/", "http://localhost:8000"), true);
});

test("isTrustedRedirect accepts a missing redirect but never a different one", () => {
  /* Evidence L8: the service may answer without a redirect value. Rejecting an
   * absent field would break every legitimate sign-in, so it is accepted and
   * logged; a present, mismatching value still rejects. */
  assert.equal(Auth.isTrustedRedirect(null, "https://example.com/"), true);
  assert.equal(Auth.isTrustedRedirect("", "https://example.com/"), true);
  assert.equal(Auth.isTrustedRedirect(undefined, "https://example.com/"), true);
});

test("extractPrivateCode reads the callback query string", () => {
  assert.equal(Auth.extractPrivateCode("?privateCode=abc"), "abc");
  assert.equal(Auth.extractPrivateCode("?publicCode=1&privateCode=abc"), "abc");
  assert.equal(Auth.extractPrivateCode("?privateCode="), null);
  assert.equal(Auth.extractPrivateCode("?otro=1"), null);
  assert.equal(Auth.extractPrivateCode(""), null);
  assert.equal(Auth.extractPrivateCode(undefined), null);
});

test("session round-trips through storage and never keeps the private code", () => {
  const storage = fakeStorage();
  Auth.writeSession(storage, { username: "narutoxd123", method: "cloud", at: 123 });

  assert.deepEqual(Auth.readSession(storage), { username: "narutoxd123", method: "cloud", at: 123 });

  const raw = storage.getItem(Auth.AUTH_SESSION_KEY);
  assert.equal(raw.includes("privateCode"), false);

  Auth.clearSession(storage);
  assert.equal(Auth.readSession(storage), null);
});

test("readSession ignores malformed or empty sessions", () => {
  assert.equal(Auth.readSession(fakeStorage()), null);
  assert.equal(Auth.readSession(null), null);
  assert.equal(Auth.readSession(fakeStorage({ [Auth.AUTH_SESSION_KEY]: "not json" })), null);
  assert.equal(Auth.readSession(fakeStorage({ [Auth.AUTH_SESSION_KEY]: "{}" })), null);
  assert.equal(Auth.readSession(fakeStorage({ [Auth.AUTH_SESSION_KEY]: '{"username":""}' })), null);
  assert.equal(Auth.readSession(fakeStorage({ [Auth.AUTH_SESSION_KEY]: '{"username":"   "}' })), null);
  assert.equal(Auth.readSession(fakeStorage({ [Auth.AUTH_SESSION_KEY]: '"texto"' })), null);
});

test("isOwnProject compares Scratch usernames case-insensitively", () => {
  assert.equal(Auth.isOwnProject("Alvaro_Games19", "alvaro_games19"), true);
  assert.equal(Auth.isOwnProject("Alvaro_Games19", "otro"), false);
  assert.equal(Auth.isOwnProject("Alvaro_Games19", null), false);
  assert.equal(Auth.isOwnProject("", "alvaro_games19"), false);
  assert.equal(Auth.isOwnProject(null, "alvaro_games19"), false);
});

test('authorLabel appends the literal "(You)" to your own projects', () => {
  assert.equal(Auth.authorLabel("Alvaro_Games19", "alvaro_games19"), "@Alvaro_Games19 (You)");
  assert.equal(Auth.authorLabel("narutoxd123", "narutoxd123"), "@narutoxd123 (You)");
  assert.equal(Auth.authorLabel("Alvaro_Games19", "otro"), "@Alvaro_Games19");
  assert.equal(Auth.authorLabel("Alvaro_Games19", null), "@Alvaro_Games19");
  assert.equal(Auth.authorLabel("", "alvaro_games19"), "");
});

test("requestTokens calls getTokens and returns the token pair", async () => {
  const calls = [];
  const fetchImpl = async (url) => {
    calls.push(url);
    return jsonResponse({ publicCode: "590022285", privateCode: "secret", authProject: 1391621033 });
  };

  const tokens = await Auth.requestTokens(fetchImpl, { redirect: "http://localhost:8000", method: "cloud" });

  assert.equal(calls.length, 1);
  const parsed = new URL(calls[0]);
  assert.equal(parsed.pathname, "/auth/getTokens");
  assert.equal(Auth.base64Decode(parsed.searchParams.get("redirect")), "http://localhost:8000");
  assert.equal(tokens.privateCode, "secret");
  assert.equal(tokens.publicCode, "590022285");
});

test("requestTokens fails loudly on a bad response", async () => {
  await assert.rejects(
    () => Auth.requestTokens(async () => jsonResponse({}, 502), { redirect: "http://x/" }),
    /getTokens/,
  );
  await assert.rejects(
    () => Auth.requestTokens(async () => jsonResponse({ publicCode: "1" }), { redirect: "http://x/" }),
    /privateCode/,
  );
});

test("requestTokens requires a username for the profile-comment method", async () => {
  let called = false;
  const fetchImpl = async () => {
    called = true;
    return jsonResponse({ privateCode: "x" });
  };

  await assert.rejects(
    () => Auth.requestTokens(fetchImpl, { redirect: "http://x/", method: "profile-comment", username: "  " }),
    /username/,
  );
  assert.equal(called, false);
});

test("verifyCode reports pending while the user has not signed in yet", async () => {
  const fetchImpl = async () => jsonResponse({ valid: false, username: null, redirect: null }, 403);
  assert.deepEqual(await Auth.verifyCode(fetchImpl, { privateCode: "abc" }), {
    valid: false,
    username: null,
    redirect: null,
  });
});

test("verifyCode returns the username once the service confirms it", async () => {
  const fetchImpl = async (url) => {
    assert.ok(url.endsWith("/auth/verifyToken/abc"));
    return jsonResponse({ valid: true, username: "narutoxd123", redirect: "http://localhost:8000/" });
  };

  assert.deepEqual(await Auth.verifyCode(fetchImpl, { privateCode: "abc" }), {
    valid: true,
    username: "narutoxd123",
    redirect: "http://localhost:8000/",
  });
});

test("verifyCode refuses a success payload without a username", async () => {
  const fetchImpl = async () => jsonResponse({ valid: true, username: null, redirect: null });
  const result = await Auth.verifyCode(fetchImpl, { privateCode: "abc" });
  assert.equal(result.valid, false);
  assert.equal(result.username, null);
});

test("verifyCode lets a network failure through so the caller can retry", async () => {
  const fetchImpl = async () => {
    throw new Error("offline");
  };
  await assert.rejects(() => Auth.verifyCode(fetchImpl, { privateCode: "abc" }), /offline/);
});

/* Added by the independent verification of T6 (odd/tasks/scratch-auth.md).
 * Two of its seven probes duplicated cases already above, so they are not
 * repeated here; these are the ones that were genuinely uncovered. */

test("isTrustedRedirect refuses a host hidden in the userinfo of our own origin", () => {
  const callback = "https://iamdantedev.github.io/basic-engine-hub/web";
  assert.equal(
    Auth.isTrustedRedirect("https://iamdantedev.github.io@evil.example/basic-engine-hub/web", callback),
    false,
  );
});

test("readSession ignores a session whose username is not a string", () => {
  const storage = fakeStorage({ [Auth.AUTH_SESSION_KEY]: JSON.stringify({ username: 12345 }) });
  assert.equal(Auth.readSession(storage), null);
});

test("a whitespace-only viewer never marks a project as yours", () => {
  assert.equal(Auth.authorLabel("Alvaro_Games19", "   "), "@Alvaro_Games19");
  assert.equal(Auth.isOwnProject("Alvaro_Games19", "   "), false);
});

test("the appended marker is the literal (You), matched case-insensitively", () => {
  assert.equal(Auth.authorLabel("narutoxd123", "NARUTOXD123"), "@narutoxd123 (You)");
  assert.match(Auth.authorLabel("narutoxd123", "narutoxd123"), /\(You\)$/);
});

test("an unknown method falls back to cloud on the wire", () => {
  const url = new URL(Auth.buildTokensUrl({ redirect: "http://x/", method: "telepathy" }));
  assert.equal(url.searchParams.get("method"), "cloud");
});
