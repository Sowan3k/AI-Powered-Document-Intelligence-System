"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button, ErrorBox, Field, inputClass } from "@/components/ui";
import { api, ApiError, saveToken } from "@/lib/api";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    const hint = setTimeout(() => setSlow(true), 5000);
    try {
      const body = await api<{ access_token: string; expires_in: number }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
      });
      saveToken(body.access_token, body.expires_in);
      const next = params.get("next");
      // Only same-site paths, never an outside URL.
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/documents");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Wrong username or password."
          : err instanceof ApiError
            ? err.message
            : "Sign-in failed.",
      );
    } finally {
      clearTimeout(hint);
      setBusy(false);
      setSlow(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <Field label="Username">
        <input name="username" autoComplete="username" required defaultValue="reviewer" className={inputClass} />
      </Field>
      <Field label="Password">
        <input name="password" type="password" autoComplete="current-password" required className={inputClass} />
      </Field>
      {error && <ErrorBox message={error} />}
      <Button type="submit" disabled={busy}>
        {busy ? "Signing in…" : "Sign in"}
      </Button>
      {slow && (
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          The backend is waking up from sleep. This can take up to a minute.
        </p>
      )}
    </form>
  );
}
