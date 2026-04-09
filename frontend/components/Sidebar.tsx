"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: "\u229e" },
  { href: "/leads", label: "Leads", icon: "\u25c8" },
  { href: "/ingest", label: "Ingest", icon: "\u2b07" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-56 flex-shrink-0 flex-col bg-slate-900">
      {/* Brand */}
      <div className="flex h-16 items-center border-b border-slate-700 px-5">
        <span className="text-sm font-semibold tracking-wide text-white">
          RSE
        </span>
        <span className="ml-2 text-xs text-slate-400">Signal Engine</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-1">
          {NAV_ITEMS.map(({ href, label, icon }) => {
            const isActive =
              href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-slate-700 text-slate-100"
                      : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                  }`}
                >
                  <span className="text-base leading-none">{icon}</span>
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Footer */}
      <div className="border-t border-slate-700 px-5 py-4">
        <p className="text-xs text-slate-500">Shelby County, AL</p>
      </div>
    </aside>
  );
}
