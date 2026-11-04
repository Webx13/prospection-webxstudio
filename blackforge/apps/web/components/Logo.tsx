interface LogoProps {
  name: string;
  className?: string;
}

/** Logo typographique provisoire : une enclume géométrique + le mot-symbole. */
export function Logo({ name, className = "" }: LogoProps) {
  return (
    <span className={`inline-flex items-center gap-3 ${className}`}>
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="h-5 w-5 text-steel-100"
        fill="currentColor"
      >
        <path d="M3 5h18v5h-4.5L15 15h3v4H6v-4h3l-1.5-5H3z" />
      </svg>
      <span className="text-[0.8125rem] font-semibold uppercase tracking-[0.34em] text-steel-100">
        {name}
      </span>
    </span>
  );
}
