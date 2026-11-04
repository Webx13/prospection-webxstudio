import { Logo } from "@/components/Logo";
import { StatusPanel } from "@/components/StatusPanel";
import { defaultLocale, getMessages } from "@/lib/i18n";
import { fetchStatus } from "@/lib/status";

// L'état de la plateforme est lu à chaque requête, jamais figé au build.
export const dynamic = "force-dynamic";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

export default async function HomePage() {
  const t = getMessages();
  const initialStatus = await fetchStatus({ baseUrl: API_INTERNAL_URL });

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col px-6 py-10 sm:px-10">
      <header className="flex items-center justify-between">
        <Logo name={t.brand.name} />
        <span className="font-mono text-xs text-steel-400">v0.1</span>
      </header>

      <div className="flex flex-1 flex-col justify-center gap-12 py-16">
        <div className="max-w-xl">
          <h1 className="text-balance text-4xl font-semibold leading-[1.1] tracking-tight text-steel-100 sm:text-5xl">
            {t.home.title}
          </h1>
          <p className="mt-6 text-pretty text-base leading-relaxed text-steel-300">{t.home.lead}</p>
        </div>

        <StatusPanel initial={initialStatus} messages={t.status} locale={defaultLocale} />
      </div>

      <footer className="border-t border-line pt-6 text-xs text-steel-400">{t.home.phaseNote}</footer>
    </main>
  );
}
