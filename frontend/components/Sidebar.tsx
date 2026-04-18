"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: "⊞" },
  { href: "/leads", label: "Leads", icon: "◈" },
  { href: "/map", label: "Map", icon: "◉" },
  { href: "/lists", label: "Lists", icon: "☆" },
  { href: "/ingest", label: "Ingest", icon: "⬇" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut, loading } = useAuth();

  function isActive(href: string) {
    return href === "/" ? pathname === "/" : pathname.startsWith(href);
  }

  async function handleSignOut() {
    await signOut();
    router.push("/");
  }

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex h-full w-56 flex-shrink-0 flex-col bg-slate-900">
        <div className="flex h-16 items-center border-b border-slate-700 px-5">
          <span className="text-sm font-semibold tracking-wide text-white">RSE</span>
          <span className="ml-2 text-xs text-slate-400">Signal Engine</span>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 py-4">
          <ul className="space-y-1">
            {NAV_ITEMS.map(({ href, label, icon }) => (
              <li key={href}>
                <Link
                  href={href}
                  className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive(href)
                      ? "bg-slate-700 text-slate-100"
                      : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                  }`}
                >
                  <span className="text-base leading-none">{icon}</span>
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        {/* User section */}
        <div className="border-t border-slate-700 px-4 py-3">
          {loading ? null : user ? (
            <div className="space-y-1">
              <p className="text-xs text-slate-400 truncate" title={user.email}>{user.email}</p>
              <button
                onClick={handleSignOut}
                className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                Sign out
              </button>
            </div>
          ) : (
            <Link href="/auth" className="text-xs text-slate-400 hover:text-slate-200 transition-colors">
              Sign in →
            </Link>
          )}
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="md:hidden fixed top-0 inset-x-0 z-40 flex h-12 items-center justify-between border-b border-slate-700 bg-slate-900 px-4">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold tracking-wide text-white">RSE</span>
          <span className="text-xs text-slate-400">Signal Engine</span>
        </div>
        {!loading && (
          user ? (
            <button onClick={handleSignOut} className="text-xs text-slate-400 hover:text-white transition-colors">
              Sign out
            </button>
          ) : (
            <Link href="/auth" className="text-xs text-slate-400 hover:text-white transition-colors">
              Sign in
            </Link>
          )
        )}
      </header>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 flex border-t border-slate-700 bg-slate-900">
        {NAV_ITEMS.map(({ href, label, icon }) => (
          <Link
            key={href}
            href={href}
            className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium transition-colors ${
              isActive(href) ? "text-white" : "text-slate-400"
            }`}
          >
            <span className="text-lg leading-none">{icon}</span>
            {label}
          </Link>
        ))}
      </nav>
    </>
  );
}
