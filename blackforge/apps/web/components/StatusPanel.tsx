"use client";

import { useState } from "react";

import type { Locale } from "@/lib/i18n";
import { fetchStatus, type DependencyState, type PlatformStatus } from "@/lib/status";
import type { Messages } from "@/messages/types";

type Tone = "ok" | "warn" | "fault";

const TONE_DOT: Record<Tone, string> = {
  ok: "bg-ok shadow-[0_0_0_3px_rgb(143_211_176/0.15)]",
  warn: "bg-warn shadow-[0_0_0_3px_rgb(217_164_65/0.15)]",
  fault: "bg-fault shadow-[0_0_0_3px_rgb(224_85_58/0.15)]",
};

function Row({ label, value, tone }: { label: string; value: string; tone?: Tone }) {
  return (
    <div className="flex items-center justify-between gap-6 py-3.5">
      <dt className="text-sm text-steel-400">{label}</dt>
      <dd className="flex items-center gap-2.5 font-mono text-sm text-steel-100">
        {tone ? <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${TONE_DOT[tone]}`} /> : null}
        {value}
      </dd>
    </div>
  );
}

function databaseTone(state: DependencyState): Tone {
  return state === "ok" ? "ok" : "fault";
}

interface StatusPanelProps {
  initial: PlatformStatus;
  messages: Messages["status"];
  /** Langue de l'application (et non celle du navigateur) pour formater l'heure. */
  locale: Locale;
}

export function StatusPanel({ initial, messages: t, locale }: StatusPanelProps) {
  const [status, setStatus] = useState<PlatformStatus>(initial);
  const [pending, setPending] = useState(false);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);

  async function refresh() {
    setPending(true);
    try {
      setStatus(await fetchStatus());
      setCheckedAt(new Date().toLocaleTimeString(locale));
    } finally {
      setPending(false);
    }
  }

  const apiTone: Tone =
    status.kind === "unreachable" ? "fault" : status.overall === "ok" ? "ok" : "warn";
  const apiLabel =
    status.kind === "unreachable"
      ? t.states.unreachable
      : status.overall === "ok"
        ? t.states.ok
        : t.states.degraded;
  const summary =
    status.kind === "unreachable"
      ? t.summary.unreachable
      : status.overall === "ok"
        ? t.summary.ok
        : t.summary.degraded;

  return (
    <section
      aria-labelledby="status-heading"
      className="rounded-xl border border-line bg-ink-800/70 p-6 sm:p-8"
    >
      <div className="flex items-center justify-between gap-4">
        <h2 id="status-heading" className="text-sm font-medium tracking-wide text-steel-100">
          {t.heading}
        </h2>
        <button
          type="button"
          onClick={refresh}
          disabled={pending}
          className="rounded-md border border-line-strong px-3.5 py-1.5 text-xs font-medium text-steel-100 transition-colors hover:bg-white/5 disabled:cursor-wait disabled:opacity-60"
        >
          {pending ? t.refreshing : t.refresh}
        </button>
      </div>

      <dl className="mt-5 divide-y divide-line">
        <Row label={t.api} value={apiLabel} tone={apiTone} />
        <Row
          label={t.database}
          value={
            status.kind === "unreachable"
              ? "—"
              : status.database === "ok"
                ? t.states.ok
                : t.states.unavailable
          }
          tone={status.kind === "unreachable" ? undefined : databaseTone(status.database)}
        />
        <Row label={t.version} value={status.kind === "unreachable" ? "—" : status.version} />
      </dl>

      <p aria-live="polite" className="mt-5 text-sm text-steel-400">
        {summary}
        {checkedAt ? <span className="ml-2 font-mono text-xs">· {t.checkedAt} {checkedAt}</span> : null}
      </p>
    </section>
  );
}
