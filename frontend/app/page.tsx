import Link from "next/link";

import { HealthStatus } from "@/components/health-status";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 px-4 py-10">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">DocIntel</h1>
        <p className="mt-1 text-neutral-600 dark:text-neutral-400">
          AI-powered document intelligence: upload invoices, extract and validate the numbers,
          and search everything.
        </p>
      </header>
      <HealthStatus />
      <div className="flex flex-wrap gap-3">
        <Link
          href="/documents"
          className="inline-flex min-h-10 items-center rounded-lg bg-neutral-900 px-4 text-sm font-medium text-white hover:bg-neutral-700 dark:bg-white dark:text-neutral-900"
        >
          Open the app
        </Link>
        <Link
          href="/login"
          className="inline-flex min-h-10 items-center rounded-lg border border-black/15 px-4 text-sm font-medium hover:bg-neutral-50 dark:border-white/20 dark:hover:bg-neutral-800"
        >
          Sign in
        </Link>
      </div>
    </main>
  );
}
