"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { ActivityProvider, useActivity } from "@/components/activity";
import { ActivityDock } from "@/components/activity-dock";
import { CompareIcon, HomeIcon, ReviewIcon, SearchIcon } from "@/components/icons";
import { API_BASE_URL, SIGNED_OUT_EVENT, clearToken, readToken } from "@/lib/api";

const TABS = [
  { href: "/documents", label: "Home", Icon: HomeIcon },
  { href: "/review", label: "Review", Icon: ReviewIcon },
  { href: "/search", label: "Search", Icon: SearchIcon },
  { href: "/reconcile", label: "Compare", Icon: CompareIcon },
];

/** Shows the app only to a signed-in user; sends everyone else to the login page. */
export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (readToken()) {
      // Reading sessionStorage is only possible after mount.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setReady(true);
    } else {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
    const onSignedOut = () => router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
  }, [router, pathname]);

  if (!ready) return null;
  return (
    <ActivityProvider>
      <TopBar pathname={pathname} />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5 px-4 pt-5 pb-36 sm:pb-10">{children}</main>
      <BottomTabs pathname={pathname} />
      <ActivityDock />
    </ActivityProvider>
  );
}

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function ReviewBadge() {
  const { activity } = useActivity();
  const count = activity?.review_count ?? 0;
  if (!count) return null;
  return (
    <span className="absolute -top-1 -right-2 min-w-5 rounded-full bg-amber-500 px-1 text-center text-[10px] font-bold leading-5 text-white">
      {count > 99 ? "99+" : count}
    </span>
  );
}

function TopBar({ pathname }: { pathname: string }) {
  const router = useRouter();
  return (
    <header className="sticky top-0 z-20 border-b border-black/10 bg-white/90 backdrop-blur dark:border-white/15 dark:bg-neutral-950/90">
      <div className="mx-auto flex max-w-5xl items-center gap-1 px-3 py-2 text-sm">
        <Link href="/documents" className="mr-3 px-1 text-base font-semibold">
          DocIntel
        </Link>
        <nav className="hidden items-center gap-1 sm:flex">
          {TABS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              aria-current={isActive(pathname, href) ? "page" : undefined}
              className={`relative rounded-md px-3 py-2 ${isActive(pathname, href) ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-900" : "hover:bg-neutral-100 dark:hover:bg-neutral-800"}`}
            >
              {label}
              {href === "/review" && <ReviewBadge />}
            </Link>
          ))}
        </nav>
        <a href={`${API_BASE_URL}/api/docs`} target="_blank" rel="noreferrer" className="ml-auto hidden rounded-md px-3 py-2 text-neutral-600 hover:bg-neutral-100 sm:block dark:text-neutral-400 dark:hover:bg-neutral-800">
          API docs
        </a>
        <button
          onClick={() => {
            clearToken();
            router.replace("/login");
          }}
          className="ml-auto rounded-md px-3 py-2 text-neutral-600 hover:bg-neutral-100 sm:ml-0 dark:text-neutral-400 dark:hover:bg-neutral-800"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}

/** Thumb-friendly tabs on phones. */
function BottomTabs({ pathname }: { pathname: string }) {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-black/10 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden dark:border-white/15 dark:bg-neutral-950/95">
      <ul className="grid grid-cols-4">
        {TABS.map(({ href, label, Icon }) => {
          const active = isActive(pathname, href);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex flex-col items-center gap-0.5 py-2 text-xs ${active ? "font-semibold text-sky-700 dark:text-sky-400" : "text-neutral-600 dark:text-neutral-400"}`}
              >
                <span className="relative">
                  <Icon className="size-6" />
                  {href === "/review" && <ReviewBadge />}
                </span>
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
