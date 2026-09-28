import { beforeEach, describe, expect, it, vi } from "vitest";
import { createController } from "../lib/controller.js";
import { fakeChrome } from "./fakeChrome.mjs";

const SITE_CHECK_OK = {
  url: "https://github.com/login",
  domain: "github.com",
  risk: 0,
  level: "low",
  decision: "autofill",
  reasons: ["Matches your saved login for github.com and the address looks clean."],
  signals: [],
  matches: [{ id: "e1", vault_id: "v1", vault: "Personal", service: "GitHub", username: "ops@acme.test" }],
  impersonates: [],
};

function fakeFetch(handlers) {
  return vi.fn(async (url, init) => {
    const path = new URL(url).pathname;
    const h = handlers[path];
    if (!h) throw new Error(`unexpected fetch: ${path}`);
    return h(init, url);
  });
}

function json(status, data) {
  return { ok: status >= 200 && status < 300, status, json: async () => data };
}

describe("controller: talking to the server", () => {
  it("sends the required header and a bearer token, never cookies", async () => {
    const chrome = fakeChrome();
    let seen;
    const fetchFn = fakeFetch({
      "/api/ext/login": (init) => {
        seen = init;
        return json(200, { token: "T1", me: { username: "olivia", org_name: "Acme" }, idle_timeout_secs: 900 });
      },
    });
    const c = createController({ chrome, fetchFn });
    const r = await c.handle({ type: "popup:login", server: "127.0.0.1:8050", username: "olivia", password: "pw" }, {});
    expect(r.ok).toBe(true);
    expect(seen.credentials).toBe("omit");
    expect(seen.headers["X-Requested-With"]).toBe("kavach");
    expect(seen.headers.Authorization).toBeUndefined(); // login itself carries no token yet
    expect(JSON.parse(seen.body)).toEqual({ username: "olivia", password: "pw" });
  });

  it("rejects a bad server address before ever calling fetch", async () => {
    const chrome = fakeChrome();
    const fetchFn = vi.fn();
    const c = createController({ chrome, fetchFn });
    const r = await c.handle({ type: "popup:login", server: "javascript:alert(1)", username: "a", password: "b" }, {});
    expect(r.ok).toBe(false);
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("surfaces mfa_required so the popup can ask for a code", async () => {
    const chrome = fakeChrome();
    const fetchFn = fakeFetch({
      "/api/ext/login": () => json(401, { error: { code: "mfa_required", message: "Enter the code." } }),
    });
    const c = createController({ chrome, fetchFn });
    const r = await c.handle({ type: "popup:login", server: "127.0.0.1:8050", username: "olivia", password: "pw" }, {});
    expect(r).toMatchObject({ ok: false, mfa: true });
  });

  it("a network failure is reported, not thrown", async () => {
    const chrome = fakeChrome();
    const fetchFn = vi.fn(async () => {
      throw new Error("boom");
    });
    const c = createController({ chrome, fetchFn });
    const r = await c.handle({ type: "popup:login", server: "127.0.0.1:8050", username: "a", password: "b" }, {});
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/cannot reach/i);
  });
});

describe("controller: sessions", () => {
  let chrome, fetchFn, c;
  beforeEach(async () => {
    chrome = fakeChrome();
    fetchFn = fakeFetch({
      "/api/ext/login": () => json(200, { token: "T1", me: { username: "olivia", org_name: "Acme" }, idle_timeout_secs: 900 }),
      "/api/ext/site-check": () => json(200, SITE_CHECK_OK),
      "/api/ext/summary": (init) =>
        init.headers.Authorization === "Bearer T1"
          ? json(200, { score: 80, label: "Good", total: 3, actions: [] })
          : json(401, { error: { code: "session_expired", message: "Sign in." } }),
    });
    c = createController({ chrome, fetchFn });
    await c.handle({ type: "popup:login", server: "127.0.0.1:8050", username: "olivia", password: "pw" }, {});
  });

  it("attaches the stored token to later requests", async () => {
    const r = await c.handle({ type: "popup:state" }, {});
    expect(r.signedIn).toBe(true);
    expect(r.summary).toEqual({ score: 80, label: "Good", total: 3, actions: [] });
  });

  it("forgets the session on a 401 and reports signed out", async () => {
    chrome._maps.session.set("token", "STALE");
    const r = await c.handle({ type: "popup:state" }, {});
    expect(r.signedIn).toBe(false);
    expect((await chrome.storage.session.get(["token"])).token).toBeUndefined();
  });

  it("popup:state with no session never calls the server", async () => {
    await c.handle({ type: "popup:logout" }, {});
    fetchFn.mockClear();
    const r = await c.handle({ type: "popup:state" }, {});
    expect(r.signedIn).toBe(false);
    expect(fetchFn).not.toHaveBeenCalled();
  });
});

describe("controller: the page address is never trusted from the message", () => {
  it("page:check ignores any url in the message and uses the sender's tab", async () => {
    const chrome = fakeChrome({ activeTabUrl: "https://real-site.example/login" });
    let sentBody;
    const fetchFn = fakeFetch({
      "/api/ext/login": () => json(200, { token: "T1", me: {}, idle_timeout_secs: 900 }),
      "/api/ext/site-check": (init) => {
        sentBody = JSON.parse(init.body);
        return json(200, { ...SITE_CHECK_OK, url: sentBody.url, matches: [] });
      },
    });
    const c = createController({ chrome, fetchFn });
    await c.handle({ type: "popup:login", server: "127.0.0.1:8050", username: "a", password: "b" }, {});
    const evil = { type: "page:check", url: "https://evil.example/attacker-controlled" };
    const r = await c.handle(evil, { tab: { id: 1, url: "https://real-site.example/login" }, frameId: 0 });
    expect(r.check.url).toBe("https://real-site.example/login");
    expect(sentBody.url).toBe("https://real-site.example/login");
  });

  it("page: messages are refused unless they come from a real tab's top frame", async () => {
    const chrome = fakeChrome();
    const c = createController({ chrome, fetchFn: fakeFetch({}) });
    expect((await c.handle({ type: "page:check" }, {})).ok).toBe(false); // no sender.tab at all
    expect((await c.handle({ type: "page:check" }, { tab: { id: 1, url: "https://x.test" }, frameId: 1 })).ok).toBe(false); // iframe
  });

  it("popup: messages are refused if they somehow come from a page", async () => {
    const chrome = fakeChrome();
    const c = createController({ chrome, fetchFn: fakeFetch({}) });
    const r = await c.handle({ type: "popup:state" }, { tab: { id: 1, url: "https://evil.example" }, frameId: 0 });
    expect(r.ok).toBe(false);
  });

  it("an unrecognized message type is refused, not silently ignored", async () => {
    const chrome = fakeChrome();
    const c = createController({ chrome, fetchFn: fakeFetch({}) });
    expect((await c.handle({ type: "popup:nonsense" }, {})).ok).toBe(false);
    expect((await c.handle(null, {})).ok).toBe(false);
    expect((await c.handle({}, {})).ok).toBe(false);
  });
});

describe("controller: filling a page", () => {
  it("page:fill passes the sender's real url and the message's vault/entry ids to /credential", async () => {
    const chrome = fakeChrome();
    let sentBody;
    const fetchFn = fakeFetch({
      "/api/ext/login": () => json(200, { token: "T1", me: {}, idle_timeout_secs: 900 }),
      "/api/ext/credential": (init) => {
        sentBody = JSON.parse(init.body);
        return json(200, { service: "GitHub", username: "ops@acme.test", password: "S3cret!" });
      },
    });
    const c = createController({ chrome, fetchFn });
    await c.handle({ type: "popup:login", server: "127.0.0.1:8050", username: "a", password: "b" }, {});
    const r = await c.handle(
      { type: "page:fill", vault_id: "v1", entry_id: "e1", confirmed: true, url: "https://attacker.example/steal" },
      { tab: { id: 1, url: "https://github.com/login" }, frameId: 0 },
    );
    expect(r).toEqual({ ok: true, service: "GitHub", username: "ops@acme.test", password: "S3cret!" });
    expect(sentBody).toEqual({ url: "https://github.com/login", vault_id: "v1", entry_id: "e1", confirmed: true });
  });

  it("a 409 from the server (needs confirmation) is reported so the UI can ask again", async () => {
    const chrome = fakeChrome();
    const fetchFn = fakeFetch({
      "/api/ext/login": () => json(200, { token: "T1", me: {}, idle_timeout_secs: 900 }),
      "/api/ext/credential": () => json(409, { error: { code: "conflict", message: "Confirm first: plain http." } }),
    });
    const c = createController({ chrome, fetchFn });
    await c.handle({ type: "popup:login", server: "127.0.0.1:8050", username: "a", password: "b" }, {});
    const r = await c.handle(
      { type: "page:fill", vault_id: "v1", entry_id: "e1" },
      { tab: { id: 1, url: "http://github.com/login" }, frameId: 0 },
    );
    expect(r).toMatchObject({ ok: false, needsConfirm: true });
  });

  it("popup:fill only messages the content script after the credential check passes", async () => {
    const chrome = fakeChrome({ activeTabUrl: "https://github.com/login" });
    const fetchFn = fakeFetch({
      "/api/ext/login": () => json(200, { token: "T1", me: {}, idle_timeout_secs: 900 }),
      "/api/ext/credential": () => json(403, { error: { code: "forbidden", message: "Kavach will not fill this page." } }),
    });
    const c = createController({ chrome, fetchFn });
    await c.handle({ type: "popup:login", server: "127.0.0.1:8050", username: "a", password: "b" }, {});
    const r = await c.handle({ type: "popup:fill", vault_id: "v1", entry_id: "e1" }, {});
    expect(r.ok).toBe(false);
    expect(chrome._messages).toHaveLength(0); // the password was never sent to the page
  });

  it("popup:fill sends the fetched credential to the active tab's content script", async () => {
    const chrome = fakeChrome({ activeTabUrl: "https://github.com/login", tabId: 7 });
    const fetchFn = fakeFetch({
      "/api/ext/login": () => json(200, { token: "T1", me: {}, idle_timeout_secs: 900 }),
      "/api/ext/credential": () => json(200, { service: "GitHub", username: "ops@acme.test", password: "S3cret!" }),
    });
    const c = createController({ chrome, fetchFn });
    await c.handle({ type: "popup:login", server: "127.0.0.1:8050", username: "a", password: "b" }, {});
    const r = await c.handle({ type: "popup:fill", vault_id: "v1", entry_id: "e1" }, {});
    expect(r).toEqual({ ok: true });
    expect(chrome._messages).toEqual([{ id: 7, msg: { type: "kavach:fill", username: "ops@acme.test", password: "S3cret!" } }]);
  });
});
