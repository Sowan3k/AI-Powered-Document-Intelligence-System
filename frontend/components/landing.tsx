"use client";

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import { CheckIcon, Mark, SearchIcon } from "@/components/icons";
import { CinematicHero } from "@/components/ui/cinematic-hero";
import { useServerWake, type Wake } from "@/components/server-wake";
import { API_BASE_URL } from "@/lib/api";
import { useLiquidGlass } from "@/lib/liquid-glass";

/**
 * The opening page (D74). The free server starts waking the moment this page
 * loads, while the visitor watches the hero. The top bar shows the real
 * status the whole time, and Sign in is always one tap away.
 */
export function Landing() {
  const wake = useServerWake();
  return (
    <div className="relative bg-background">
      <TopBar wake={wake} />
      <ScrollHint />
      <CinematicHero
        brandName="DocIntel"
        tagline1="Invoices in."
        tagline2="Checked data out."
        cardHeading="Every number, checked."
        cardDescription="Gemini reads PDFs, scans, phone photos and spreadsheets. Python checks every sum in exact decimals. Only invoices with a doubt reach a person."
        metricValue={11}
        metricLabel="checks per invoice"
        ctaHeading="Try it on your own files."
        ctaDescription={<CtaText wake={wake} />}
        ctaActions={<Actions />}
        phoneHeader={<PhoneHeader />}
        phoneWidgets={<PhoneWidgets />}
        badges={<Badges wake={wake} />}
        contentClassName="pt-[calc(max(0.75rem,env(safe-area-inset-top))+3.5rem)] lg:pt-0"
      />
      {/* Reduced motion: the hero stays still and shows no call to action, so it comes here. */}
      <section className="hidden flex-col items-center gap-6 px-4 py-20 text-center motion-reduce:flex">
        <h2 className="type-display text-4xl">Try it on your own files.</h2>
        <p className="max-w-xl text-muted">
          <CtaText wake={wake} />
        </p>
        <div className="flex flex-row flex-wrap justify-center gap-3">
          <Actions />
        </div>
      </section>
      <footer className="flex flex-col items-center gap-2 px-4 pt-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] text-center text-xs text-muted">
        <div className="flex items-center gap-2">
          <Mark className="size-5" />
          <span className="font-medium text-foreground">DocIntel</span>
        </div>
        <p>FastAPI, PostgreSQL with pgvector, Gemini and Next.js.</p>
      </footer>
    </div>
  );
}

function CtaText({ wake }: { wake: Wake }) {
  return (
    <>
      Sign in with the demo account from the submission email, then upload a PDF, a photo or a spreadsheet.
      <span className={`mt-3 block text-sm ${wake.ready ? "text-emerald-600 dark:text-emerald-400" : ""}`}>
        {wake.ready ? "The server is awake and ready." : `The server is waking in the background · ${wake.seconds} s.`}
      </span>
    </>
  );
}

function Actions() {
  return (
    <>
      <Link href="/login" className="btn-modern-light inline-flex items-center justify-center rounded-full px-7 py-3.5 text-base font-semibold sm:px-8 sm:py-4">
        Sign in
      </Link>
      <a
        href={`${API_BASE_URL}/api/docs`}
        target="_blank"
        rel="noreferrer"
        className="btn-modern-dark inline-flex items-center justify-center rounded-full px-7 py-3.5 text-base font-semibold sm:px-8 sm:py-4"
      >
        API docs
      </a>
    </>
  );
}

/** Fixed above the hero, so the status and Sign in never scroll away. */
function TopBar({ wake }: { wake: Wake }) {
  const lost = wake.steps.some((s) => s.state === "error");
  const dot = wake.ready ? "bg-emerald-400" : lost ? "bg-rose-400" : "animate-pulse bg-current opacity-60";
  const barRef = useRef<HTMLDivElement | null>(null);
  const glass = useLiquidGlass<HTMLDivElement>();
  const onDark = useOverDarkCard(barRef);
  const setRefs = useCallback(
    (el: HTMLDivElement | null) => {
      barRef.current = el;
      return glass(el);
    },
    [glass],
  );
  return (
    <header className="fixed inset-x-0 top-[max(0.75rem,env(safe-area-inset-top))] z-[60] px-3">
      <motion.div
        ref={setRefs}
        initial={{ opacity: 0, y: -14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 320, damping: 30, delay: 0.2 }}
        className={`glass glass-still mx-auto flex max-w-5xl items-center justify-between gap-2 rounded-full py-1.5 pr-1.5 pl-3 transition-colors duration-300 ${onDark ? "glass-on-dark" : ""}`}
      >
        <span className="flex items-center gap-2">
          <Mark className="size-7" />
          <span className="text-[15px] font-semibold tracking-tight">DocIntel</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span role="status" aria-live="polite" className="flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-medium tabular-nums">
            <span className={`size-2 rounded-full ${dot}`} aria-hidden />
            <span className="sm:hidden">{wake.ready ? "Ready" : lost ? "Not answering" : `${wake.seconds} s`}</span>
            <span className="hidden sm:inline">{wake.short}</span>
          </span>
          <Link
            href="/login"
            className={`rounded-full px-4 py-2 text-sm font-semibold transition-colors duration-300 hover:opacity-85 ${onDark ? "bg-white text-slate-900" : "bg-foreground text-background"}`}
          >
            Sign in
          </Link>
        </span>
      </motion.div>
    </header>
  );
}

/**
 * True while the hero's dark card is under the element. Clear glass shows
 * what is behind it, so text on it must switch to light over the card, as
 * iOS does with its glass (D76).
 */
function useOverDarkCard(ref: RefObject<HTMLElement | null>): boolean {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const el = ref.current;
    const card = document.querySelector(".main-card");
    if (!el || !card) return;
    let observer: IntersectionObserver | null = null;
    // The browser tells us when the card crosses a 1 px line through the
    // middle of the bar. It accounts for transforms, and needs no work per frame.
    const watch = () => {
      observer?.disconnect();
      const r = el.getBoundingClientRect();
      const mid = Math.round(r.top + r.height / 2);
      observer = new IntersectionObserver(([entry]) => setDark(entry.isIntersecting), {
        rootMargin: `${-mid}px 0px ${-(window.innerHeight - mid - 1)}px 0px`,
      });
      observer.observe(card);
    };
    watch();
    window.addEventListener("resize", watch);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", watch);
    };
  }, [ref]);
  return dark;
}

/**
 * A clear nudge on the first screen, sitting on the card that peeks up from
 * the bottom edge. It leaves as soon as the visitor scrolls (D75).
 */
function ScrollHint() {
  const [show, setShow] = useState(true);
  const [touch, setTouch] = useState(false);
  const pillGlass = useLiquidGlass<HTMLSpanElement>();
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read once from the device
    setTouch(window.matchMedia("(pointer: coarse)").matches);
    const onScroll = () => setShow(window.scrollY < 24);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0, transition: { delay: 1.4, type: "spring", stiffness: 260, damping: 24 } }}
          exit={{ opacity: 0, y: 12, transition: { duration: 0.2 } }}
          aria-hidden
          className="pointer-events-none fixed inset-x-0 bottom-[calc(max(1rem,env(safe-area-inset-bottom))+4svh)] z-[60] flex justify-center motion-reduce:hidden"
        >
          <span ref={pillGlass} className="glass glass-still glass-on-dark flex items-center gap-2.5 rounded-full py-2.5 pr-5 pl-3 text-sm font-semibold">
            <span className="relative grid size-7 place-items-center overflow-hidden rounded-full bg-brand text-white">
              <motion.svg
                viewBox="0 0 24 24"
                className="size-4 fill-none stroke-current stroke-[2.5]"
                animate={{ y: touch ? [5, -5, 5] : [-5, 5, -5] }}
                transition={{ duration: 1.3, repeat: Infinity, ease: "easeInOut" }}
              >
                <path d={touch ? "M6 15l6-6 6 6" : "M6 9l6 6 6-6"} strokeLinecap="round" strokeLinejoin="round" />
              </motion.svg>
            </span>
            {touch ? "Swipe up to see it work" : "Scroll to see it work"}
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function PhoneHeader() {
  return (
    <div className="flex items-center justify-between">
      <span className="flex items-center gap-2">
        <Mark className="size-5" />
        <span className="text-[13px] font-semibold">Review</span>
      </span>
      <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-medium text-white/70">1 to check</span>
    </div>
  );
}

const widget = "phone-widget widget-depth rounded-2xl p-3";

function PhoneWidgets() {
  return (
    <>
      <div className={widget}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-mono text-[10px] text-white/45">INV-2026-00004</p>
            <p className="truncate text-[13px] font-semibold">Blue River Stationers</p>
          </div>
          <p className="text-[13px] font-semibold tabular-nums">£428.75</p>
        </div>
        <p className="mt-2 flex items-center gap-1.5 text-[11px] text-rose-300">
          <span className="size-1.5 rounded-full bg-rose-400" aria-hidden />
          R05 · Total ≠ subtotal + tax
        </p>
      </div>
      <div className={widget}>
        <div className="flex items-center gap-2 rounded-xl bg-white/[0.06] px-2.5 py-1.5 text-[11px] text-white/75">
          <SearchIcon className="size-3.5 text-emerald-300" />
          printer supplies
        </div>
        <p className="mt-2 text-[11px] text-white/50">3 matches · keyword and meaning</p>
      </div>
      <div className={widget}>
        <p className="text-[10px] font-semibold tracking-[0.18em] text-white/40 uppercase">Reads</p>
        <div className="mt-1.5 flex flex-wrap gap-1">
          {["PDF", "Scan", "Photo", "Excel", "CSV"].map((k) => (
            <span key={k} className="rounded-md bg-white/[0.07] px-1.5 py-0.5 text-[10px] font-medium text-white/80">
              {k}
            </span>
          ))}
        </div>
      </div>
    </>
  );
}

/** Two glass badges beside the phone. The first is the live server status. */
function Badges({ wake }: { wake: Wake }) {
  return (
    <>
      <div className="absolute top-[14%] right-1/2 z-30 mr-[100px] md:mr-[120px] lg:mr-[150px]">
        <div className="floating-badge floating-ui-badge flex items-center gap-3 rounded-2xl py-3 pr-4 pl-3 text-white">
          <span className={`grid size-9 shrink-0 place-items-center rounded-xl ${wake.ready ? "bg-emerald-400/20" : "bg-white/10"}`}>
            {wake.ready ? (
              <CheckIcon className="size-4 text-emerald-300" />
            ) : (
              <span className="size-4 animate-spin rounded-full border-2 border-white/25 border-t-white" aria-hidden />
            )}
          </span>
          <span className="flex flex-col">
            <span className="text-[10px] font-semibold tracking-[0.16em] text-white/45 uppercase">Live server</span>
            <span className="text-sm font-semibold whitespace-nowrap tabular-nums">{wake.short}</span>
          </span>
        </div>
      </div>
      <div className="absolute bottom-[16%] left-1/2 z-30 ml-[100px] md:ml-[120px] lg:ml-[150px]">
        <div className="floating-badge floating-ui-badge flex items-center gap-3 rounded-2xl py-3 pr-4 pl-3 text-white">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-amber-300/15 text-sm font-bold text-amber-200">2×</span>
          <span className="flex flex-col">
            <span className="text-[10px] font-semibold tracking-[0.16em] text-white/45 uppercase">Duplicate caught</span>
            <span className="text-sm font-semibold whitespace-nowrap">Same bill, new layout</span>
          </span>
        </div>
      </div>
    </>
  );
}
