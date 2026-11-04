import { describe, expect, it } from "vitest";

import { defaultLocale, getMessages, isLocale, locales } from "@/lib/i18n";

function leafPaths(value: unknown, prefix = ""): string[] {
  if (typeof value === "string") return [prefix];
  if (typeof value !== "object" || value === null) return [];
  return Object.entries(value).flatMap(([key, child]) =>
    leafPaths(child, prefix ? `${prefix}.${key}` : key),
  );
}

describe("i18n", () => {
  it("la langue par défaut est le français", () => {
    expect(defaultLocale).toBe("fr");
  });

  it("chaque langue expose exactement les mêmes clés", () => {
    const reference = leafPaths(getMessages("fr")).sort();
    for (const locale of locales) {
      expect(leafPaths(getMessages(locale)).sort()).toEqual(reference);
    }
  });

  it("aucune traduction n'est vide", () => {
    for (const locale of locales) {
      const flat = JSON.stringify(getMessages(locale));
      expect(flat).not.toContain('""');
    }
  });

  it("isLocale refuse les valeurs inconnues", () => {
    expect(isLocale("fr")).toBe(true);
    expect(isLocale("en")).toBe(true);
    expect(isLocale("de")).toBe(false);
    expect(isLocale("")).toBe(false);
  });
});
