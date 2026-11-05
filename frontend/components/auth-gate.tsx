"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { ActivityProvider, useActivity } from "@/components/activity";
import { ActivityDock } from "@/components/activity-dock";
import { CompareIcon, HomeIcon, Mark, ReviewIcon, SearchIcon } from "@/components/icons";
import { direction } from "@/components/page-transition";
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
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5 px-4 pt-5 pb-48 sm:pb-24">{children}</main>
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
    <motion.span
      key={count}
      initial={{ scale: 0.6, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 500, damping: 22 }}
      className="absolute -top-1.5 -right-2.5 min-w-5 rounded-full bg-amber-500 px-1 text-center text-[10px] font-bold leading-5 text-white shadow-[0_0_0_2px_var(--background)]"
    >
      {count > 99 ? "99+" : count}
    </motion.span>
  );
}

const lensSpring = { type: "spring", stiffness: 420, damping: 34, mass: 0.8 } as const;

function TopBar({ pathname }: { pathname: string }) {
  const router = useRouter();
  return (
    <header
      style={{ viewTransitionName: "app-header" }}
      className="glass sticky top-0 z-20 rounded-none border-x-0 border-t-0 pt-[env(safe-area-inset-top)]"
    >
      <div className="mx-auto flex max-w-5xl items-center gap-1 px-3 py-2 text-sm">
        <Link href="/documents" transitionTypes={direction(pathname, "/documents")} className="mr-3 flex items-center gap-2 px-1 text-base font-semibold tracking-tight">
          <Mark />
          DocIntel
        </Link>
        <nav className="hidden items-center gap-1 sm:flex">
          {TABS.map(({ href, label }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                transitionTypes={direction(pathname, href)}
                aria-current={active ? "page" : undefined}
                className={`relative rounded-full px-3.5 py-1.5 transition-colors ${active ? "text-foreground" : "text-muted hover:text-foreground"}`}
              >
                {active && <motion.span layoutId="top-lens" transition={lensSpring} className="glass-lens absolute inset-0 -z-10 rounded-full" />}
                {label}
                {href === "/review" && <ReviewBadge />}
              </Link>
            );
          })}
        </nav>
        <a href={`${API_BASE_URL}/api/docs`} target="_blank" rel="noreferrer" className="ml-auto hidden rounded-full px-3 py-1.5 text-muted transition-colors hover:text-foreground sm:block">
          API docs
        </a>
        <button
          onClick={() => {
            clearToken();
            router.replace("/login");
          }}
          className="ml-auto rounded-full px-3 py-1.5 text-muted transition-colors hover:text-foreground sm:ml-0"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}

/** Thumb-friendly tabs on phones: a floating glass bar with a lens that slides to the active tab. */
function BottomTabs({ pathname }: { pathname: string }) {
  return (
    <nav className="fixed inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-20 sm:hidden">
      {/* The name sits on the glass itself: on an ancestor it would stop the blur (D73). */}
      <ul style={{ viewTransitionName: "app-tabs" }} className="glass grid grid-cols-4 gap-1 rounded-[1.75rem] p-1.5">
        {TABS.map(({ href, label, Icon }) => {
          const active = isActive(pathname, href);
          return (
            <li key={href} className="relative">
              {active && <motion.span layoutId="tab-lens" transition={lensSpring} className="glass-lens absolute inset-0 rounded-[1.35rem]" />}
              <Link
                href={href}
                transitionTypes={direction(pathname, href)}
                aria-current={active ? "page" : undefined}
                className={`relative flex flex-col items-center gap-0.5 rounded-[1.35rem] py-1.5 text-[11px] transition-colors ${active ? "font-semibold text-foreground" : "text-muted"}`}
              >
                <motion.span className="relative" animate={{ scale: active ? 1.08 : 1 }} transition={lensSpring}>
                  <Icon className="size-6" />
                  {href === "/review" && <ReviewBadge />}
                </motion.span>
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
