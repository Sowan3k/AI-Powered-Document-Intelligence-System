import { Suspense } from "react";

import { LoginForm } from "@/components/login-form";
import { ServerStatus } from "@/components/server-status";

export default function LoginPage() {
  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-6 px-4 py-10">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Sign in to DocIntel</h1>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">Use the demo account from the submission email.</p>
      </header>
      <ServerStatus />
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
