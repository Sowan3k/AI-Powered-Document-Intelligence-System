"use client";

import { motion, type Variants } from "motion/react";
import { Suspense } from "react";

import { Mark } from "@/components/icons";
import { LoginForm } from "@/components/login-form";
import { ScanPreview } from "@/components/scan-preview";
import { WakeIsland, WakeTimeline, useServerWake } from "@/components/server-wake";
import { API_BASE_URL } from "@/lib/api";
import { SIGN_IN_BACKGROUND } from "@/lib/brand";
import { ThemeToggle } from "@/components/theme-toggle";

const rise: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: (i: number) => ({ opacity: 1, y: 0, transition: { delay: 0.08 * i, type: "spring", stiffness: 260, damping: 28 } }),
};

/**
 * The first screen a reviewer sees, usually while the free server wakes up.
 * It shows what DocIntel does (a live preview), how far the wake-up has got,
 * and lets them sign in at once (D73).
 */
export function LoginScreen() {
  const wake = useServerWake();
  return (
    <div className="relative flex min-h-dvh flex-1 flex-col">
      <Backdrop />
      <WakeIsland wake={wake} />
      {/* Light and dark start here; the opening page keeps to the phone's setting (D81). */}
      <div className="fixed top-[max(0.75rem,env(safe-area-inset-top))] right-3 z-50">
        <ThemeToggle className="glass text-foreground" />
      </div>
      {/* Phones: the form comes first, the pitch and preview below it (D75). Wide screens: side by side. */}
      <main className="mx-auto grid w-full max-w-5xl flex-1 content-start gap-6 px-4 pt-[calc(max(0.75rem,env(safe-area-inset-top))+3.75rem)] pb-10 lg:grid-cols-[1.1fr_1fr] lg:content-center lg:gap-x-14 lg:gap-y-6">
        <motion.header custom={0} variants={rise} initial="hidden" animate="show" className="lg:col-start-1 lg:row-start-1">
          <div className="flex items-center gap-2.5">
            <Mark className="size-9" />
            <span className="text-2xl font-semibold tracking-tight">DocIntel</span>
          </div>
          <h1 className="type-display mt-5 hidden text-6xl lg:block">
            Invoices in.
            <br />
            <span className="text-muted">Checked data out.</span>
          </h1>
          <p className="mt-4 hidden max-w-md text-base text-muted lg:block">
            DocIntel reads invoices from PDFs, scans, photos and spreadsheets. Python checks every number,
            and a person sees only what needs a look.
          </p>
        </motion.header>

        <motion.section
          custom={1}
          variants={rise}
          initial="hidden"
          animate="show"
          className="glass-strong flex flex-col gap-5 rounded-[2rem] p-6 sm:p-7 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:self-center"
        >
          <div>
            <h2 className="type-section">Sign in</h2>
            <p className="mt-1 text-sm text-muted">Use the demo account from the submission email.</p>
          </div>
          <WakeTimeline wake={wake} />
          <Suspense>
            <LoginForm />
          </Suspense>
          <p className="text-center text-xs text-muted">
            <a href={`${API_BASE_URL}/api/docs`} target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">
              API docs
            </a>
          </p>
        </motion.section>

        <motion.div custom={2} variants={rise} initial="hidden" animate="show" className="lg:col-start-1 lg:row-start-2">
          <p className="type-eyebrow mb-3 text-muted lg:hidden">What happens to an invoice</p>
          <ScanPreview />
        </motion.div>
      </main>
    </div>
  );
}

/** The chosen photo when there is one; otherwise brighter light and a faint grid. */
function Backdrop() {
  if (SIGN_IN_BACKGROUND) {
    return (
      <div aria-hidden className="fixed inset-0 -z-[1]">
        {/* eslint-disable-next-line @next/next/no-img-element -- a full-bleed decorative background */}
        <img src={SIGN_IN_BACKGROUND} alt="" className="size-full object-cover" fetchPriority="high" />
        <div className="absolute inset-0 bg-gradient-to-b from-white/40 via-white/55 to-white/80 dark:from-black/45 dark:via-black/60 dark:to-black/85" />
      </div>
    );
  }
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-[1] overflow-hidden">
      <motion.div
        className="absolute -top-40 left-1/2 size-[42rem] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgb(196_150_62/0.18),rgb(15_27_45/0.05)_55%,transparent)]"
        animate={{ scale: [1, 1.12, 1], opacity: [0.8, 1, 0.8] }}
        transition={{ duration: 9, repeat: Infinity, ease: "easeInOut" }}
      />
      <div className="absolute inset-0 [background-image:linear-gradient(to_right,rgb(127_127_127/0.08)_1px,transparent_1px),linear-gradient(to_bottom,rgb(127_127_127/0.08)_1px,transparent_1px)] [background-size:44px_44px] [mask-image:radial-gradient(ellipse_at_top,black_20%,transparent_70%)]" />
    </div>
  );
}
