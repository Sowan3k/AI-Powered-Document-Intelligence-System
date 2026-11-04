"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { API_BASE_URL, SIGNED_OUT_EVENT, clearToken, readToken } from "@/lib/api";

const LINKS = [
  { href: "/documents", label: "Documents" },
  { href: "/upload", label: "Upload" },
  { href: "/review", label: "Review" },
  { href: "/search", label: "Search" },
  { href: "/reconcile", label: "Reconcile" },
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
    <>
      <Nav pathname={pathname} />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5 px-4 py-6">{children}</main>
    </>
  );
}

function Nav({ pathname }: { pathname: string }) {
  const router = useRouter();
  return (
    <nav className="sticky top-0 z-10 border-b border-black/10 bg-white/90 backdrop-blur dark:border-white/15 dark:bg-neutral-950/90">
      <div className="mx-auto flex max-w-5xl items-center gap-1 overflow-x-auto px-2 py-2 text-sm">
        <Link href="/" className="mr-2 px-2 font-semibold">
          DocIntel
        </Link>
        {LINKS.map((link) => {
          const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? "page" : undefined}
              className={`whitespace-nowrap rounded-md px-3 py-2 ${active ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-900" : "hover:bg-neutral-100 dark:hover:bg-neutral-800"}`}
            >
              {link.label}
            </Link>
          );
        })}
        <a
          href={`${API_BASE_URL}/api/docs`}
          target="_blank"
          rel="noreferrer"
          className="whitespace-nowrap rounded-md px-3 py-2 hover:bg-neutral-100 dark:hover:bg-neutral-800"
        >
          API docs
        </a>
        <button
          onClick={() => {
            clearToken();
            router.replace("/login");
          }}
          className="ml-auto whitespace-nowrap rounded-md px-3 py-2 text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
        >
          Sign out
        </button>
      </div>
    </nav>
  );
}
