import { describe, expect, it } from "vitest";
import type { IntelEntry } from "./api";
import { decisionOf, groupByPriority, LEVEL, mfaCoverage, riskText } from "./intel";

const entry = (id: string, priority: string) => ({ ref: { id }, priority }) as unknown as IntelEntry;

describe("riskText", () => {
  it("reads like the product copy: 18/100 — Low", () => {
    expect(riskText(18, "low")).toBe("18/100 — Low");
    expect(riskText(92, "critical")).toBe("92/100 — Critical");
    expect(riskText(50, "mystery")).toBe("50/100 — mystery");
  });
});

describe("groupByPriority", () => {
  it("orders groups critical → low and drops empty ones", () => {
    const groups = groupByPriority([entry("a", "low"), entry("b", "critical"), entry("c", "low"), entry("d", "medium")]);
    expect(groups.map((g) => g.priority)).toEqual(["critical", "medium", "low"]);
    expect(groups.find((g) => g.priority === "low")?.entries.map((e) => e.ref.id)).toEqual(["a", "c"]);
  });
  it("is empty for no entries", () => {
    expect(groupByPriority([])).toEqual([]);
  });
});

describe("decisionOf", () => {
  it("maps each engine decision to a label and tone", () => {
    expect(decisionOf("autofill").tone).toBe("success");
    expect(decisionOf("confirm").tone).toBe("warning");
    expect(decisionOf("block").tone).toBe("danger");
    expect(decisionOf("no_match").tone).toBe("neutral");
  });
  it("never crashes on an unknown decision", () => {
    expect(decisionOf("something-new").label).toBe(decisionOf("no_match").label);
  });
});

describe("mfaCoverage", () => {
  it("shows how many critical accounts are covered", () => {
    expect(mfaCoverage(5, 3)).toBe("2 of 5");
    expect(mfaCoverage(0, 0)).toBe("n/a");
  });
});

describe("LEVEL colours", () => {
  it("has a colour for every level the engine produces", () => {
    for (const l of ["low", "medium", "elevated", "high", "critical"]) expect(LEVEL[l]?.color).toMatch(/^var\(--/);
  });
});
