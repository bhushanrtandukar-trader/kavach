import { describe, expect, it } from "vitest";
import { gradientFor, initials, plural, relativeTime, safeHost, serviceLetters, serviceStyle } from "./utils";

const NOW = 1_800_000_000_000; // ms
const ago = (secs: number) => NOW / 1000 - secs;

describe("relativeTime", () => {
  it("says 'never' when there is no timestamp", () => {
    expect(relativeTime(null)).toBe("never");
    expect(relativeTime(undefined)).toBe("never");
    expect(relativeTime(0)).toBe("never");
  });
  it("is 'just now' for the last few seconds, in either direction", () => {
    expect(relativeTime(ago(5), NOW)).toBe("just now");
    expect(relativeTime(ago(-20), NOW)).toBe("just now");
  });
  it("picks a sensible unit", () => {
    expect(relativeTime(ago(120), NOW)).toBe("2 minutes ago");
    expect(relativeTime(ago(3 * 3600), NOW)).toBe("3 hours ago");
    expect(relativeTime(ago(86_400), NOW)).toBe("yesterday");
    expect(relativeTime(ago(10 * 86_400), NOW)).toBe("last week");
    expect(relativeTime(ago(-2 * 3600), NOW)).toBe("in 2 hours");
  });
});

describe("names and colours", () => {
  it("makes initials from one or several words", () => {
    expect(initials("Olivia Owner")).toBe("OO");
    expect(initials("olivia")).toBe("OL");
    expect(initials("  Mary Jane Watson ")).toBe("MW");
    expect(initials("")).toBe("?");
  });
  it("gives the same gradient for the same name, case-insensitively", () => {
    expect(gradientFor("Ops")).toBe(gradientFor("ops"));
    expect(gradientFor("Ops")).toMatch(/^linear-gradient\(/);
  });
  it("spreads different names across several gradients", () => {
    const set = new Set(["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"].map(gradientFor));
    expect(set.size).toBeGreaterThan(3);
  });
  it("uses brand colours for well-known services and gradients otherwise", () => {
    expect(serviceStyle("GitHub").background).toContain("#24292e");
    expect(serviceStyle("My AWS account").background).toContain("#ff9900");
    expect(serviceStyle("Some internal tool").background).toMatch(/^linear-gradient/);
  });
  it("abbreviates service names", () => {
    expect(serviceLetters("GitHub")).toBe("G");
    expect(serviceLetters("Bank portal")).toBe("BP");
    expect(serviceLetters("")).toBe("?");
  });
});

describe("plural", () => {
  it("handles one and many", () => {
    expect(plural(1, "entry", "entries")).toBe("1 entry");
    expect(plural(0, "entry", "entries")).toBe("0 entries");
    expect(plural(2, "member")).toBe("2 members");
    expect(plural(1234, "event")).toBe("1,234 events");
  });
});

describe("safeHost — which entry URLs may become links", () => {
  it("accepts http and https, with or without a scheme", () => {
    expect(safeHost("https://www.github.com/login")).toEqual({ href: "https://www.github.com/login", host: "github.com" });
    expect(safeHost("github.com")).toEqual({ href: "https://github.com/", host: "github.com" });
    expect(safeHost("http://ci.acme.test:8080/x")?.host).toBe("ci.acme.test");
  });
  it("refuses script and data URLs, whatever the case", () => {
    for (const evil of ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<script>alert(1)</script>", "vbscript:x", "file:///etc/passwd", "ftp://example.com"]) {
      expect(safeHost(evil), evil).toBeNull();
    }
  });
  it("refuses nonsense without throwing", () => {
    expect(safeHost("")).toBeNull();
    expect(safeHost("http://")).toBeNull();
  });
});
