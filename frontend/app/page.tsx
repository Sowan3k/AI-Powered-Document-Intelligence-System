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
    </main>
  );
}
