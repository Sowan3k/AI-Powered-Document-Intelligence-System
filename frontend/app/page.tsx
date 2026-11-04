"use client";

import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { LoginForm } from "@/components/login-form";
import { ServerStatus } from "@/components/server-status";
import { readToken } from "@/lib/api";

/** Signed in: straight to Home. Otherwise: sign in right here, no extra page. */
export default function Start() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    if (readToken()) router.replace("/documents");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    else setChecked(true);
  }, [router]);
  if (!checked) return null;
  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-6 px-4 py-10">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">DocIntel</h1>
        <p className="mt-2 text-neutral-600 dark:text-neutral-400">
          Drop invoices, receipts, scans or spreadsheets. DocIntel reads them, checks the numbers
          and tells you what needs a look.
        </p>
      </header>
      <ServerStatus />
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
