"use client";

import { motion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ErrorBox, Field, inputClass } from "@/components/ui";
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
      {error && (
        <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0, x: [0, -6, 6, -3, 3, 0] }} transition={{ duration: 0.4 }}>
          <ErrorBox message={error} />
        </motion.div>
      )}
      <motion.button
        type="submit"
        disabled={busy}
        whileTap={{ scale: 0.97 }}
        className="relative inline-flex min-h-12 items-center justify-center gap-2 overflow-hidden rounded-2xl btn-primary px-4 font-semibold transition disabled:opacity-70"
      >
        {busy && (
          <motion.span
            className="size-4 rounded-full border-2 border-white/40 border-t-white"
            animate={{ rotate: 360 }}
            transition={{ repeat: Infinity, duration: 0.8, ease: "linear" }}
          />
        )}
        {busy ? "Signing in…" : "Sign in"}
      </motion.button>
      {slow && <p className="text-sm text-muted">The server is still waking up. Your sign-in will go through when it is ready.</p>}
    </form>
  );
}
