import { en } from "@/messages/en";
import { fr } from "@/messages/fr";
import type { Messages } from "@/messages/types";

export const locales = ["fr", "en"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "fr";

const catalogs: Record<Locale, Messages> = { fr, en };

export function isLocale(value: string): value is Locale {
  return (locales as readonly string[]).includes(value);
}

export function getMessages(locale: Locale = defaultLocale): Messages {
  return catalogs[locale];
}
