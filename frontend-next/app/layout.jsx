import "../styles/globals.css";
import { Inter } from "next/font/google";

const inter = Inter({ subsets: ["latin"], display: "swap" });

export const metadata = {
  title: "Pre-Sales NETS Enterprise Solution",
  description: "NETS International presales and tender intelligence",
};

/**
 * Root layout. EVERYTHING renders inside #nets-next-root / .nets-next:
 * that wrapper is the scoping contract from tailwind.config.js. Removing it
 * removes all styling on purpose.
 */
export default function RootLayout({ children }) {
  return (
    <html lang="en" className={inter.className}>
      <body style={{ margin: 0 }}>
        <div id="nets-next-root" className="nets-next min-h-screen bg-slate-50 dark:bg-slate-950">
          {/* Header: white surface so the official NETS logo keeps its colours */}
          <header className="sticky top-0 z-30 border-b-2 border-brand bg-white">
            <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-5">
              {/* Official NETS logo: served from /public/nets-logo.png, the
                  original asset. Never recreated, stretched or recoloured. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/nets-logo.png" alt="NETS International" className="h-10 w-auto" />
              <div className="min-w-0">
                <p className="truncate text-[15px] font-extrabold tracking-tight text-slate-900">
                  Leadership Command Centre
                </p>
                <p className="truncate text-[11.5px] uppercase tracking-widest text-slate-400">
                  Pre-Sales &amp; Tender Intelligence
                </p>
              </div>
              <nav className="ml-auto flex items-center gap-1">
                <a href="/" className="rounded-lg px-3 py-2 text-[13px] font-semibold text-slate-600 hover:bg-slate-50 hover:text-brand">
                  Overview
                </a>
                <a href="/leadership" className="rounded-lg px-3 py-2 text-[13px] font-semibold text-slate-600 hover:bg-slate-50 hover:text-brand">
                  Leadership
                </a>
                <a href="/knowledge" className="rounded-lg px-3 py-2 text-[13px] font-semibold text-slate-600 hover:bg-slate-50 hover:text-brand">
                  Knowledge bank
                </a>
              </nav>
            </div>
          </header>
          <main className="mx-auto max-w-7xl px-5 py-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
