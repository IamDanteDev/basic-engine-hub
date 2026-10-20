"use strict";

/* Basic Engine Hub — sign-in core (Scratch Auth plus the PenguinMod bio check).
 *
 * Pure helpers with no DOM and no implicit globals, so the `node --test`
 * suite can exercise every rule. web/app.js owns the DOM wiring.
 *
 * Scratch flow (documented at https://auth.itinerary.eu.org/documentation/introduction,
 * real spec in Looky1173/Scratch-Auth-Client src/docs/custom-frontend.mdx):
 *   1. GET {AUTH_API_BASE}/auth/getTokens?method=&redirect=<base64>&authProject=
 *      -> {publicCode, privateCode, redirectLocation, method, authProject}
 *   2. The user enters `publicCode` in AUTH_PROJECT_URL (or comments it).
 *   3. GET {AUTH_API_BASE}/auth/verifyToken/<privateCode>
 *      -> {valid:false} while pending, {valid:true, username, redirect} once done.
 *
 * The base64 `redirect` is percent-encoded on the wire. Raw base64 is not safe:
 * a "+" decodes as a space and silently corrupts the URL (evidence L6 in
 * odd/tasks/scratch-auth.md).
 *
 * The PenguinMod identity is the second channel, web only (S7 in the same
 * document): there is no service behind it, the code is pasted into the user's
 * own profile bio and read back from the public profile endpoint. Its section
 * below carries the evidence and the limits of what that channel can prove.
 */

const AUTH_API_BASE = "https://auth-api.itinerary.eu.org";
const AUTH_PROJECT_ID = 1391621033;
const AUTH_PROJECT_URL = `https://scratch.mit.edu/projects/${AUTH_PROJECT_ID}/`;
const AUTH_METHODS = ["cloud", "comment", "profile-comment"];
const AUTH_SESSION_KEY = "basic-engine-hub:sesion:v1";
/* The service's own frontend refreshes tokens every 5 minutes (TOKEN_VALIDITY). */
const AUTH_CODE_TTL_MS = 5 * 60 * 1000;

function isKnownMethod(method) {
  return AUTH_METHODS.includes(String(method));
}

function base64Encode(text) {
  const bytes = new TextEncoder().encode(String(text));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64Decode(text) {
  try {
    const binary = atob(String(text));
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
}

/* The page the service has to send the user back to: origin + path, no trailing
 * slash and no query, so the value we send and the value we check are identical. */
function buildCallbackUrl(location) {
  const origin = String(location?.origin || "").replace(/\/+$/, "");
  const path = String(location?.pathname || "/").replace(/\/+$/, "");
  return `${origin}${path}`;
}

function encodeRedirect(url) {
  return base64Encode(url);
}

function buildTokensUrl({ apiBase = AUTH_API_BASE, redirect, method = "cloud", authProject = AUTH_PROJECT_ID, username = "" } = {}) {
  const params = new URLSearchParams();
  params.set("method", isKnownMethod(method) ? method : "cloud");
  params.set("redirect", encodeRedirect(redirect));
  params.set("authProject", String(authProject));
  if (String(method) === "profile-comment" && String(username).trim()) {
    params.set("username", String(username).trim());
  }
  return `${apiBase}/auth/getTokens?${params.toString()}`;
}

function verifyUrl({ apiBase = AUTH_API_BASE, privateCode } = {}) {
  return `${apiBase}/auth/verifyToken/${encodeURIComponent(String(privateCode))}`;
}

function normalizeUrl(value) {
  try {
    const url = new URL(String(value));
    const path = url.pathname.replace(/\/+$/, "");
    return `${url.protocol}//${url.host}${path}${url.search}`;
  } catch {
    return "";
  }
}

/* Anti-phishing check the documentation insists on: the verified identity must
 * belong to the redirect location we asked for.
 *
 * A missing value is accepted (and the caller warns): our privateCode was
 * requested by this very page, so the token is already bound to us, and
 * rejecting an absent field would break every legitimate sign-in. A value that
 * is present and points somewhere else rejects the sign-in. */
function isTrustedRedirect(returned, expected) {
  if (returned === null || returned === undefined || returned === "") return true;
  const target = normalizeUrl(expected);
  if (!target) return false;
  const decoded = base64Decode(returned);
  return [returned, decoded].some((candidate) => candidate && normalizeUrl(candidate) === target);
}

function extractPrivateCode(search) {
  try {
    const value = new URLSearchParams(String(search || "")).get("privateCode");
    return value ? value : null;
  } catch {
    return null;
  }
}

function readSession(storage) {
  try {
    const raw = storage && storage.getItem(AUTH_SESSION_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw);
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const username = typeof value.username === "string" ? value.username.trim() : "";
    if (!username) return null;
    return {
      username,
      method: typeof value.method === "string" ? value.method : "",
      at: Number(value.at) || 0,
    };
  } catch {
    return null;
  }
}

function writeSession(storage, session) {
  const username = String(session?.username || "").trim();
  if (!username) return null;
  const value = { username, method: String(session?.method || ""), at: Number(session?.at) || Date.now() };
  storage.setItem(AUTH_SESSION_KEY, JSON.stringify(value));
  return value;
}

function clearSession(storage) {
  if (storage) storage.removeItem(AUTH_SESSION_KEY);
}

function isOwnProject(projectUsername, sessionUsername) {
  const author = String(projectUsername || "").trim().toLowerCase();
  const viewer = String(sessionUsername || "").trim().toLowerCase();
  return author !== "" && viewer !== "" && author === viewer;
}

/* Scratch usernames are case-insensitive, so compare them that way. */
function authorLabel(username, sessionUsername) {
  const name = String(username || "").trim();
  if (!name) return "";
  return isOwnProject(name, sessionUsername) ? `@${name} (You)` : `@${name}`;
}

async function requestTokens(fetchImpl, { apiBase, redirect, method = "cloud", authProject, username = "" } = {}) {
  if (isPenguinModMethod(method)) {
    /* Its code is generated in the page; the service must never see it. */
    throw new Error("profile-bio never reaches the Scratch Auth service");
  }
  if (String(method) === "profile-comment" && !String(username).trim()) {
    throw new Error("profile-comment requires the Scratch username");
  }
  const response = await fetchImpl(buildTokensUrl({ apiBase, redirect, method, authProject, username }));
  if (!response || !response.ok) {
    throw new Error(`getTokens failed with HTTP ${response ? response.status : "?"}`);
  }
  const tokens = await response.json();
  if (!tokens || !tokens.privateCode) throw new Error("getTokens returned no privateCode");
  return tokens;
}

async function verifyCode(fetchImpl, { apiBase, privateCode } = {}) {
  const response = await fetchImpl(verifyUrl({ apiBase, privateCode }));
  /* A pending sign-in answers 403 with {"valid":false}; that is not an error. */
  if (!response || !response.ok) return { valid: false, username: null, redirect: null };
  const data = await response.json();
  const username = data && typeof data.username === "string" ? data.username : "";
  const valid = Boolean(data && data.valid === true && username);
  return {
    valid,
    username: valid ? username : null,
    redirect: data && data.redirect ? data.redirect : null,
  };
}

/* ---- PenguinMod identity (profile bio, web only) ---------------------------
 *
 * There is no service to ask here. PenguinMod's cloud is TurboWarp's anonymous
 * cloud and its backend exposes no comments API, so neither can carry a name
 * worth trusting. The one surface that is public, owner-writable and readable
 * from the browser is the profile bio, verified live against production:
 *
 *   GET https://projects.penguinmod.com/api/v1/users/profile?target=<user>
 *   -> 200 {"success":true,"username","bio","privateProfile":false,...}, with
 *      access-control-allow-origin: *, so the browser calls it directly with
 *      no proxy -- the same condition the Scratch Auth service meets in S5.
 *   -> 404 {"error":"NotFound"} both for a missing user and for a private
 *      profile, which the endpoint does not separate: one reason covers both.
 *
 * So the code is ours, generated in the page, and the user pastes it into
 * their own bio. What that proves is exactly "the owner of that profile put
 * this code there" -- no more: the bio is public, so anyone reading the
 * profile reads the code. That is enough to label a session, and it is why
 * this method ships on the web only (S7): in the desktop app it would claim
 * more than the channel can carry. */
const PENGUINMOD_API_BASE = "https://projects.penguinmod.com";
const PENGUINMOD_PROFILE_URL = "https://penguinmod.com/profile";
const PENGUINMOD_METHOD = "profile-bio";
/* No 0/O and no 1/I: the code is read off the screen and retyped by hand. 32
 * symbols also keep 256 % 32 === 0, so the byte-to-symbol mapping is bias-free. */
const PENGUINMOD_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const PENGUINMOD_CODE_LENGTH = 8;

function isPenguinModMethod(method) {
  return String(method) === PENGUINMOD_METHOD;
}

function buildProfileUrl({ apiBase = PENGUINMOD_API_BASE, username = "" } = {}) {
  const name = String(username).trim();
  if (!name) throw new Error("profile-bio requires the PenguinMod username");
  return `${apiBase}/api/v1/users/profile?target=${encodeURIComponent(name)}`;
}

/* A standalone token: "BEH2345" must not count inside "BEH23456" or "XBEH2345".
 * Lookbehind would say this in one regex, but Safari only gained it in 16.4 and
 * this menu runs on whatever family tablet shows up, so the neighbours are
 * checked by hand. Case-insensitive because a bio pasted from a phone may come
 * back in another case, and the code carries no case information anyway. */
function bioHasCode(bio, code) {
  const haystack = String(bio || "").toLowerCase();
  const needle = String(code || "").trim().toLowerCase();
  if (!haystack || !needle) return false;
  let index = haystack.indexOf(needle);
  while (index !== -1) {
    const before = index === 0 ? "" : haystack[index - 1];
    const after = haystack.slice(index + needle.length, index + needle.length + 1);
    if (!/[a-z0-9]/.test(before) && !/[a-z0-9]/.test(after)) return true;
    index = haystack.indexOf(needle, index + 1);
  }
  return false;
}

/* The random source is injected so the test can pin the alphabet and the
 * length; the browser passes window.crypto.getRandomValues bound to crypto. */
function generateCode(randomValues) {
  const bytes = randomValues(PENGUINMOD_CODE_LENGTH);
  let code = "";
  for (let index = 0; index < PENGUINMOD_CODE_LENGTH; index += 1) {
    code += PENGUINMOD_CODE_ALPHABET[bytes[index] % PENGUINMOD_CODE_ALPHABET.length];
  }
  return code;
}

async function verifyBio(fetchImpl, { apiBase, username, code } = {}) {
  const response = await fetchImpl(buildProfileUrl({ apiBase, username }));
  if (!response || !response.ok) {
    /* 404 means missing user or private profile; anything else is the request
     * failing, which the caller retries rather than reports as a verdict. */
    return {
      valid: false,
      username: null,
      reason: response && response.status === 404 ? "not-found" : "unreachable",
    };
  }
  const data = await response.json();
  const asked = String(username || "").trim().toLowerCase();
  const found = data && typeof data.username === "string" ? data.username.trim() : "";
  /* The endpoint echoes the user it looked up. Anything else is not the
   * identity we asked about, and must never become our session. */
  if (!found || found.toLowerCase() !== asked) return { valid: false, username: null, reason: "mismatch" };
  if (!bioHasCode(data.bio, code)) return { valid: false, username: null, reason: "pending" };
  return { valid: true, username: found, reason: "" };
}

/* Where the session chip points. A session stored before this method existed
 * carries an empty method and stays a Scratch one. */
function profileUrl(session) {
  const username = String(session?.username || "").trim();
  if (!username) return "";
  if (isPenguinModMethod(session.method)) {
    return `${PENGUINMOD_PROFILE_URL}?user=${encodeURIComponent(username)}`;
  }
  return `https://scratch.mit.edu/users/${encodeURIComponent(username)}/`;
}

/* A PenguinMod session proves a PenguinMod identity, so it must never earn the
 * "(You)" marker on a Scratch project, however alike the two names look. */
function claimsScratchProjects(session) {
  return Boolean(session) && !isPenguinModMethod(session.method);
}

const AuthCore = {
  AUTH_API_BASE,
  AUTH_PROJECT_ID,
  AUTH_PROJECT_URL,
  AUTH_METHODS,
  AUTH_SESSION_KEY,
  AUTH_CODE_TTL_MS,
  PENGUINMOD_API_BASE,
  PENGUINMOD_PROFILE_URL,
  PENGUINMOD_METHOD,
  PENGUINMOD_CODE_ALPHABET,
  PENGUINMOD_CODE_LENGTH,
  isKnownMethod,
  base64Encode,
  base64Decode,
  buildCallbackUrl,
  encodeRedirect,
  buildTokensUrl,
  verifyUrl,
  isTrustedRedirect,
  extractPrivateCode,
  readSession,
  writeSession,
  clearSession,
  isOwnProject,
  authorLabel,
  requestTokens,
  verifyCode,
  isPenguinModMethod,
  buildProfileUrl,
  bioHasCode,
  generateCode,
  verifyBio,
  profileUrl,
  claimsScratchProjects,
};

if (typeof module !== "undefined" && module.exports) module.exports = AuthCore;
