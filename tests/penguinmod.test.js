"use strict";

/* Tests for the PenguinMod sign-in core in web/auth.js (S7 in
 * odd/tasks/scratch-auth.md). There is no service to ask: the page generates
 * the code, the user pastes it into their own profile bio, and the page reads
 * it back through the public profile endpoint, which answers with
 * access-control-allow-origin: * so the browser calls it with no proxy.
 *
 * Everything here is pure; the fetch is injected, so no test touches the
 * network.
 *
 * Run with: node --test
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const Auth = require("../web/auth.js");

/* Verified live against production: a public profile answers
 * {"success":true,"username","bio","privateProfile":false,...}; a missing user
 * and a private profile both answer 404 {"error":"NotFound"}, so they cannot be
 * told apart and share one reason. */
const PROFILE_API = "https://projects.penguinmod.com/api/v1/users/profile";

function profileResponse(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) };
}

test("the profile url points at the public endpoint and encodes the username", () => {
  assert.equal(Auth.buildProfileUrl({ username: "danteelgamer_yt" }), `${PROFILE_API}?target=danteelgamer_yt`);
  assert.equal(Auth.buildProfileUrl({ username: "Dante el Gamer" }), `${PROFILE_API}?target=Dante%20el%20Gamer`);
  assert.throws(() => Auth.buildProfileUrl({}), /username/, "no username means no profile to read");
  assert.throws(() => Auth.buildProfileUrl({ username: "   " }), /username/);
});

test("the code counts only as a standalone token of the bio", () => {
  assert.equal(Auth.bioHasCode("mi codigo es BEH2345 ok", "BEH2345"), true);
  assert.equal(Auth.bioHasCode("BEH2345", "BEH2345"), true);
  assert.equal(Auth.bioHasCode("beh2345", "BEH2345"), true, "a bio pasted in another case still holds the code");
  assert.equal(Auth.bioHasCode("BEH23456", "BEH2345"), false, "a longer run of characters is not the code");
  assert.equal(Auth.bioHasCode("XBEH2345", "BEH2345"), false);
  assert.equal(Auth.bioHasCode("", "BEH2345"), false);
  assert.equal(Auth.bioHasCode("hola", ""), false, "an empty code must never match");
});

test("the code is eight characters of an alphabet without look-alikes", () => {
  const alphabet = Auth.PENGUINMOD_CODE_ALPHABET;
  assert.equal(alphabet.length, 32, "32 symbols keep 256 % 32 === 0, so the mapping has no modulo bias");
  assert.ok(!/[0OI1]/.test(alphabet), "the user retypes the code by hand: no 0/O, no 1/I");
  assert.equal(Auth.generateCode(() => [0, 1, 2, 3, 4, 5, 6, 7]), "ABCDEFGH");
  assert.equal(Auth.generateCode(() => [31, 31, 31, 31, 31, 31, 31, 31]), "99999999");
});

test("the session is valid once the bio carries the code", async () => {
  const calls = [];
  const result = await Auth.verifyBio(
    (url) => {
      calls.push(url);
      return Promise.resolve(
        profileResponse({ success: true, username: "Danteelgamer_YT", bio: "¡Hola! codigo BEH2345 listo", privateProfile: false }),
      );
    },
    { username: "danteelgamer_yt", code: "BEH2345" },
  );
  assert.deepEqual(result, { valid: true, username: "Danteelgamer_YT", reason: "" });
  assert.equal(calls.length, 1);
  assert.equal(calls[0], `${PROFILE_API}?target=danteelgamer_yt`, "the code must not travel in the request");
});

test("a bio without the code keeps the sign-in waiting", async () => {
  const result = await Auth.verifyBio(
    () => Promise.resolve(profileResponse({ success: true, username: "dante", bio: "sin codigo", privateProfile: false })),
    { username: "dante", code: "BEH2345" },
  );
  assert.deepEqual(result, { valid: false, username: null, reason: "pending" });
});

test("a missing user and a private profile share the reason the API cannot separate", async () => {
  for (const username of ["noexiste999", "perfil-privado"]) {
    const result = await Auth.verifyBio(
      () => Promise.resolve(profileResponse({ error: "NotFound" }, 404)),
      { username, code: "BEH2345" },
    );
    assert.deepEqual(result, { valid: false, username: null, reason: "not-found" });
  }
});

test("a profile that is not the one asked for never signs the session in", async () => {
  const result = await Auth.verifyBio(
    () => Promise.resolve(profileResponse({ success: true, username: "otro", bio: "codigo BEH2345", privateProfile: false })),
    { username: "dante", code: "BEH2345" },
  );
  assert.deepEqual(result, { valid: false, username: null, reason: "mismatch" });
});

test("a failed profile request rejects so the caller keeps waiting", async () => {
  await assert.rejects(
    () => Auth.verifyBio(() => Promise.reject(new Error("network down")), { username: "dante", code: "BEH2345" }),
    /network down/,
  );
});

test("the session chip links to the profile of its own service", () => {
  assert.equal(Auth.profileUrl({ username: "dante", method: "profile-comment" }), "https://scratch.mit.edu/users/dante/");
  assert.equal(Auth.profileUrl({ username: "dante", method: "profile-bio" }), "https://penguinmod.com/profile?user=dante");
  assert.equal(
    Auth.profileUrl({ username: "dante", method: "" }),
    "https://scratch.mit.edu/users/dante/",
    "a session stored before this feature stays a Scratch one",
  );
  assert.equal(Auth.profileUrl(null), "");
});

test("a PenguinMod session never claims a Scratch project as its own", () => {
  assert.equal(Auth.isPenguinModMethod("profile-bio"), true);
  assert.equal(Auth.isPenguinModMethod("cloud"), false);
  assert.equal(Auth.isPenguinModMethod(""), false);
  assert.equal(Auth.claimsScratchProjects({ username: "dante", method: "profile-bio" }), false);
  assert.equal(Auth.claimsScratchProjects({ username: "dante", method: "comment" }), true);
  assert.equal(Auth.claimsScratchProjects(null), false);
});

test("the Scratch Auth service never receives the PenguinMod method", async () => {
  assert.equal(Auth.isKnownMethod("profile-bio"), false, "the service knows three methods, not four");
  const url = Auth.buildTokensUrl({ redirect: "https://x.test/", method: "profile-bio" });
  assert.ok(url.includes("method=cloud"), "an unknown method degrades to cloud");
  assert.equal(url.includes("profile-bio"), false);
  assert.equal(url.includes("profile%2Dbio"), false);
  await assert.rejects(
    () => Auth.requestTokens(() => Promise.resolve({ ok: true, status: 200 }), { redirect: "https://x.test/", method: "profile-bio" }),
    /never reaches the Scratch Auth service/,
    "its code is generated in the page; asking the service for one would be a different flow",
  );
});
