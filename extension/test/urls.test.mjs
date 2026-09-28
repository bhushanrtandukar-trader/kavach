import { describe, expect, it } from "vitest";
import { hostOf, normalizeServer, pageForCheck } from "../lib/urls.js";

describe("normalizeServer", () => {
  it("accepts a plain https address", () => {
    expect(normalizeServer("kavach.acme.test")).toEqual({ ok: true, origin: "https://kavach.acme.test" });
    expect(normalizeServer("https://kavach.acme.test/")).toEqual({ ok: true, origin: "https://kavach.acme.test" });
  });

  it("allows plain http only for the local machine", () => {
    expect(normalizeServer("127.0.0.1:8050")).toEqual({ ok: true, origin: "http://127.0.0.1:8050" });
    expect(normalizeServer("localhost:8050")).toEqual({ ok: true, origin: "http://localhost:8050" });
    expect(normalizeServer("http://kavach.acme.test")).toMatchObject({ ok: false });
  });

  it("refuses anything that is not http(s)", () => {
    expect(normalizeServer("ftp://kavach.acme.test")).toMatchObject({ ok: false });
    expect(normalizeServer("javascript:alert(1)")).toMatchObject({ ok: false });
    expect(normalizeServer("not a url")).toMatchObject({ ok: false });
    expect(normalizeServer("")).toMatchObject({ ok: false });
    expect(normalizeServer("   ")).toMatchObject({ ok: false });
  });

  it("refuses embedded credentials", () => {
    expect(normalizeServer("https://user:pass@kavach.acme.test")).toMatchObject({ ok: false });
  });

  it("drops a trailing path so /api/ext concatenation is not doubled", () => {
    expect(normalizeServer("https://kavach.acme.test/some/path")).toEqual({ ok: true, origin: "https://kavach.acme.test" });
  });
});

describe("pageForCheck", () => {
  it("keeps scheme, host and path only", () => {
    expect(pageForCheck("https://github.com/login?next=/x#frag")).toBe("https://github.com/login");
    expect(pageForCheck("https://user:pass@github.com/login")).toBe("https://github.com/login");
  });

  it("rejects non-web schemes", () => {
    for (const u of ["chrome://settings", "file:///etc/passwd", "chrome-extension://abc/x.html", "about:blank", "data:text/html,x"]) {
      expect(pageForCheck(u)).toBeNull();
    }
  });

  it("rejects garbage", () => {
    expect(pageForCheck("")).toBeNull();
    expect(pageForCheck(undefined)).toBeNull();
    expect(pageForCheck("not a url")).toBeNull();
  });

  it("truncates a very long path instead of sending it whole", () => {
    const long = "https://example.com/" + "a".repeat(5000);
    const out = pageForCheck(long);
    expect(out.length).toBeLessThan(400);
  });
});

describe("hostOf", () => {
  it("extracts the host, and is safe on garbage", () => {
    expect(hostOf("https://github.com/login")).toBe("github.com");
    expect(hostOf("not a url")).toBe("");
    expect(hostOf(undefined)).toBe("");
  });
});
