import type { NextConfig } from "next";

// Cible du proxy de développement /api/v1/* → API. Évaluée au BUILD (les rewrites sont
// figés dans le manifeste de routes). En production, un reverse proxy route /api vers l'API
// et ces réécritures ne servent plus ; voir docs/01-ARCHITECTURE.md.
const apiInternalUrl = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

// CSP volontairement absente à ce stade : elle sera introduite avec des nonces lorsque
// Monaco et React Flow (qui injectent styles et workers) seront intégrés. Voir docs/03-SECURITY.md.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${apiInternalUrl}/api/v1/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
