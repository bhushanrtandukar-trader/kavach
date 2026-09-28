import { beforeEach, describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
// detect.js attaches itself to globalThis; load it once into this module's global scope.
new Function(fs.readFileSync(path.join(here, "../content/detect.js"), "utf8"))();
const D = globalThis.KavachDetect;

function setBody(html) {
  document.body.innerHTML = html;
}

describe("findLogins", () => {
  beforeEach(() => setBody(""));

  it("pairs a password field with the username field above it", () => {
    setBody(`<form><input name="email"><input name="pw" type="password"></form>`);
    const logins = D.findLogins(document, { layout: false });
    expect(logins).toHaveLength(1);
    expect(logins[0].username.name).toBe("email");
    expect(logins[0].password.name).toBe("pw");
  });

  it("finds a bare password field with no form", () => {
    setBody(`<input name="u"><input name="pw" type="password">`);
    expect(D.findLogins(document, { layout: false })).toHaveLength(1);
  });

  it("prefers a field whose autocomplete says username over a nearer decoy", () => {
    setBody(`<form>
      <input name="search" type="text">
      <input name="user" autocomplete="username">
      <input name="pw" type="password">
    </form>`);
    const [login] = D.findLogins(document, { layout: false });
    expect(login.username.name).toBe("user");
  });

  it("skips fields that look like search, OTP or promo codes", () => {
    setBody(`<form>
      <input name="search" placeholder="Search the site">
      <input name="promo" placeholder="Promo code">
      <input name="pw" type="password">
    </form>`);
    const [login] = D.findLogins(document, { layout: false });
    expect(login.username).toBeNull();
  });

  it("ignores a hidden password field (a common autofill trap)", () => {
    setBody(`<form><input name="u"><input name="pw" type="password" style="display:none"></form>`);
    expect(D.findLogins(document, { layout: false })).toHaveLength(0);
  });

  it("ignores a password field with visibility:hidden or near-zero opacity", () => {
    setBody(`
      <form><input name="pw1" type="password" style="visibility:hidden"></form>
      <form><input name="pw2" type="password" style="opacity:0"></form>
    `);
    expect(D.findLogins(document, { layout: false })).toHaveLength(0);
  });

  it("ignores a password field disabled or marked readonly", () => {
    setBody(`
      <form><input name="pw1" type="password" disabled></form>
      <form><input name="pw2" type="password" readonly></form>
    `);
    expect(D.findLogins(document, { layout: false })).toHaveLength(0);
  });

  it("treats a hidden ancestor as hidden too, not just the field itself", () => {
    setBody(`<div style="display:none"><form><input name="u"><input name="pw" type="password"></form></div>`);
    expect(D.findLogins(document, { layout: false })).toHaveLength(0);
  });

  it("skips a sign-up form (autocomplete=new-password)", () => {
    setBody(`<form><input name="u"><input name="pw" type="password" autocomplete="new-password"></form>`);
    expect(D.findLogins(document, { layout: false })).toHaveLength(0);
  });

  it("skips a change-password form with two visible password fields", () => {
    setBody(`<form>
      <input name="old" type="password">
      <input name="new" type="password">
    </form>`);
    expect(D.findLogins(document, { layout: false })).toHaveLength(0);
  });

  it("does not treat another password field as a username candidate", () => {
    setBody(`<form>
      <input name="pw" type="password" autocomplete="new-password" style="display:none">
      <input name="pw2" type="password">
    </form>`);
    // the hidden decoy is ignored entirely, and it is a password field so it is never offered as a username
    const logins = D.findLogins(document, { layout: false });
    if (logins.length) expect(logins[0].username).toBeNull();
  });

  it("finds multiple independent login forms on one page", () => {
    setBody(`
      <form id="a"><input name="u1"><input name="p1" type="password"></form>
      <form id="b"><input name="u2"><input name="p2" type="password"></form>
    `);
    expect(D.findLogins(document, { layout: false })).toHaveLength(2);
  });
});

describe("fill", () => {
  it("sets both fields and fires input/change so frameworks notice", () => {
    setBody(`<form><input name="u"><input name="pw" type="password"></form>`);
    const [login] = D.findLogins(document, { layout: false });
    const events = [];
    login.username.addEventListener("input", () => events.push("u:input"));
    login.password.addEventListener("change", () => events.push("p:change"));
    const r = D.fill(login, { username: "olivia", password: "S3cret!" });
    expect(r).toEqual({ username: true, password: true });
    expect(login.username.value).toBe("olivia");
    expect(login.password.value).toBe("S3cret!");
    expect(events).toEqual(["u:input", "p:change"]);
  });

  it("fills only the password when there is no username field to fill", () => {
    setBody(`<input name="pw" type="password">`);
    const [login] = D.findLogins(document, { layout: false });
    const r = D.fill(login, { username: "olivia", password: "S3cret!" });
    expect(r).toEqual({ username: false, password: true });
  });
});
