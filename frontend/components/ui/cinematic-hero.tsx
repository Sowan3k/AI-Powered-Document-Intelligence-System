"use client";

// A scroll-driven landing hero: two lines of headline, then a deep card rises,
// fills the screen, and an iPhone mockup flies in with widgets and floating
// badges, before a call to action. Adapted from a shared shadcn-style
// component (D74): the content comes in through props, the phone screen and
// badges are slots, and people who ask for reduced motion get a still layout.

import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import React, { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger);
}

const INJECTED_STYLES = `
  .gsap-reveal { visibility: hidden; }

  .film-grain {
      position: absolute; inset: 0; width: 100%; height: 100%;
      pointer-events: none; z-index: 50; opacity: 0.05; mix-blend-mode: overlay;
      background: url('data:image/svg+xml;utf8,<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg"><filter id="noiseFilter"><feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="3" stitchTiles="stitch"/></filter><rect width="100%" height="100%" filter="url(%23noiseFilter)"/></svg>');
  }

  .bg-grid-theme {
      background-size: 60px 60px;
      background-image:
          linear-gradient(to right, color-mix(in srgb, var(--color-foreground) 5%, transparent) 1px, transparent 1px),
          linear-gradient(to bottom, color-mix(in srgb, var(--color-foreground) 5%, transparent) 1px, transparent 1px);
      mask-image: radial-gradient(ellipse at center, black 0%, transparent 70%);
      -webkit-mask-image: radial-gradient(ellipse at center, black 0%, transparent 70%);
  }

  .text-3d-matte {
      color: var(--color-foreground);
      text-shadow:
          0 10px 30px color-mix(in srgb, var(--color-foreground) 20%, transparent),
          0 2px 4px color-mix(in srgb, var(--color-foreground) 10%, transparent);
  }

  .text-silver-matte {
      background: linear-gradient(180deg, var(--color-foreground) 0%, color-mix(in srgb, var(--color-foreground) 40%, transparent) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      transform: translateZ(0);
      filter:
          drop-shadow(0px 10px 20px color-mix(in srgb, var(--color-foreground) 15%, transparent))
          drop-shadow(0px 2px 4px color-mix(in srgb, var(--color-foreground) 10%, transparent));
  }

  .text-card-silver-matte {
      background: linear-gradient(180deg, #FFFFFF 0%, #A1A1AA 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      transform: translateZ(0);
      filter:
          drop-shadow(0px 12px 24px rgba(0,0,0,0.8))
          drop-shadow(0px 4px 8px rgba(0,0,0,0.6));
  }

  .premium-depth-card {
      background: linear-gradient(145deg, #162C6D 0%, #0A101D 100%);
      box-shadow:
          0 40px 100px -20px rgba(0, 0, 0, 0.9),
          0 20px 40px -20px rgba(0, 0, 0, 0.8),
          inset 0 1px 2px rgba(255, 255, 255, 0.2),
          inset 0 -2px 4px rgba(0, 0, 0, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.04);
      position: relative;
  }

  .card-sheen {
      position: absolute; inset: 0; border-radius: inherit; pointer-events: none; z-index: 50;
      background: radial-gradient(800px circle at var(--mouse-x, 50%) var(--mouse-y, 50%), rgba(255,255,255,0.06) 0%, transparent 40%);
      mix-blend-mode: screen; transition: opacity 0.3s ease;
  }

  .iphone-bezel {
      background-color: #111;
      box-shadow:
          inset 0 0 0 2px #52525B,
          inset 0 0 0 7px #000,
          0 40px 80px -15px rgba(0,0,0,0.9),
          0 15px 25px -5px rgba(0,0,0,0.7);
      transform-style: preserve-3d;
  }

  .hardware-btn {
      background: linear-gradient(90deg, #404040 0%, #171717 100%);
      box-shadow:
          -2px 0 5px rgba(0,0,0,0.8),
          inset -1px 0 1px rgba(255,255,255,0.15),
          inset 1px 0 2px rgba(0,0,0,0.8);
      border-left: 1px solid rgba(255,255,255,0.05);
  }

  .screen-glare {
      background: linear-gradient(110deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0) 45%);
  }

  .widget-depth {
      background: linear-gradient(180deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%);
      box-shadow:
          0 10px 20px rgba(0,0,0,0.3),
          inset 0 1px 1px rgba(255,255,255,0.05),
          inset 0 -1px 1px rgba(0,0,0,0.5);
      border: 1px solid rgba(255,255,255,0.03);
  }

  .floating-ui-badge {
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.08) 0%, rgba(255, 255, 255, 0.01) 100%);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      box-shadow:
          0 0 0 1px rgba(255, 255, 255, 0.1),
          0 25px 50px -12px rgba(0, 0, 0, 0.8),
          inset 0 1px 1px rgba(255,255,255,0.2),
          inset 0 -1px 1px rgba(0,0,0,0.5);
  }

  .btn-modern-light, .btn-modern-dark {
      transition: all 0.4s cubic-bezier(0.25, 1, 0.5, 1);
  }
  .btn-modern-light {
      background: linear-gradient(180deg, #FFFFFF 0%, #F1F5F9 100%);
      color: #0F172A;
      box-shadow: 0 0 0 1px rgba(0,0,0,0.05), 0 2px 4px rgba(0,0,0,0.1), 0 12px 24px -4px rgba(0,0,0,0.3), inset 0 1px 1px rgba(255,255,255,1), inset 0 -3px 6px rgba(0,0,0,0.06);
  }
  .btn-modern-light:hover {
      transform: translateY(-3px);
      box-shadow: 0 0 0 1px rgba(0,0,0,0.05), 0 6px 12px -2px rgba(0,0,0,0.15), 0 20px 32px -6px rgba(0,0,0,0.4), inset 0 1px 1px rgba(255,255,255,1), inset 0 -3px 6px rgba(0,0,0,0.06);
  }
  .btn-modern-light:active {
      transform: translateY(1px);
      background: linear-gradient(180deg, #F1F5F9 0%, #E2E8F0 100%);
      box-shadow: 0 0 0 1px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.1), inset 0 3px 6px rgba(0,0,0,0.1), inset 0 0 0 1px rgba(0,0,0,0.02);
  }
  .btn-modern-dark {
      background: linear-gradient(180deg, #27272A 0%, #18181B 100%);
      color: #FFFFFF;
      box-shadow: 0 0 0 1px rgba(255,255,255,0.1), 0 2px 4px rgba(0,0,0,0.6), 0 12px 24px -4px rgba(0,0,0,0.9), inset 0 1px 1px rgba(255,255,255,0.15), inset 0 -3px 6px rgba(0,0,0,0.8);
  }
  .btn-modern-dark:hover {
      transform: translateY(-3px);
      background: linear-gradient(180deg, #3F3F46 0%, #27272A 100%);
      box-shadow: 0 0 0 1px rgba(255,255,255,0.15), 0 6px 12px -2px rgba(0,0,0,0.7), 0 20px 32px -6px rgba(0,0,0,1), inset 0 1px 1px rgba(255,255,255,0.2), inset 0 -3px 6px rgba(0,0,0,0.8);
  }
  .btn-modern-dark:active {
      transform: translateY(1px);
      background: #18181B;
      box-shadow: 0 0 0 1px rgba(255,255,255,0.05), inset 0 3px 8px rgba(0,0,0,0.9), inset 0 0 0 1px rgba(0,0,0,0.5);
  }

  .progress-ring {
      transform: rotate(-90deg);
      transform-origin: center;
      stroke-dasharray: 402;
      stroke-dashoffset: 402;
      stroke-linecap: round;
  }
`;

export interface CinematicHeroProps extends React.HTMLAttributes<HTMLDivElement> {
  brandName?: string;
  tagline1?: string;
  tagline2?: string;
  cardHeading?: string;
  cardDescription?: React.ReactNode;
  metricValue?: number;
  metricLabel?: string;
  ctaHeading?: string;
  ctaDescription?: React.ReactNode;
  /** Buttons or links under the call to action. */
  ctaActions?: React.ReactNode;
  /** Widgets inside the phone, under the ring. Give each the class "phone-widget". */
  phoneWidgets?: React.ReactNode;
  /** A line at the top of the phone screen, such as the app's name. */
  phoneHeader?: React.ReactNode;
  /** Badges that float around the phone. Give each the class "floating-badge". */
  badges?: React.ReactNode;
  /** Extra classes for the card's content, such as room for a fixed top bar. */
  contentClassName?: string;
}

export function CinematicHero({
  brandName = "Brand",
  tagline1 = "First line,",
  tagline2 = "second line.",
  cardHeading = "A heading.",
  cardDescription = "A description.",
  metricValue = 100,
  metricLabel = "Metric",
  ctaHeading = "Get started.",
  ctaDescription = "",
  ctaActions,
  phoneWidgets,
  phoneHeader,
  badges,
  contentClassName,
  className,
  ...props
}: CinematicHeroProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mainCardRef = useRef<HTMLDivElement>(null);
  const mockupRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef<number>(0);

  // 1. Mouse lighting and phone tilt, once per frame at most.
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const handleMouseMove = (e: MouseEvent) => {
      if (window.scrollY > window.innerHeight * 2) return;
      cancelAnimationFrame(requestRef.current);
      requestRef.current = requestAnimationFrame(() => {
        if (!mainCardRef.current || !mockupRef.current) return;
        const rect = mainCardRef.current.getBoundingClientRect();
        mainCardRef.current.style.setProperty("--mouse-x", `${e.clientX - rect.left}px`);
        mainCardRef.current.style.setProperty("--mouse-y", `${e.clientY - rect.top}px`);
        const xVal = (e.clientX / window.innerWidth - 0.5) * 2;
        const yVal = (e.clientY / window.innerHeight - 0.5) * 2;
        gsap.to(mockupRef.current, { rotationY: xVal * 12, rotationX: -yVal * 12, ease: "power3.out", duration: 1.2 });
      });
    };
    window.addEventListener("mousemove", handleMouseMove);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      cancelAnimationFrame(requestRef.current);
    };
  }, []);

  // 2. The scroll timeline. Reduced motion gets the finished card, still.
  useEffect(() => {
    const isMobile = window.innerWidth < 768;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const ctx = gsap.context(() => {
      if (reduce) {
        gsap.set([".hero-text-wrapper", ".cta-wrapper"], { autoAlpha: 0 });
        gsap.set([".main-card", ".card-left-text", ".card-right-text", ".mockup-scroll-wrapper", ".floating-badge", ".phone-widget"], { autoAlpha: 1 });
        gsap.set(".progress-ring", { strokeDashoffset: 60 });
        gsap.set(".counter-val", { innerHTML: metricValue });
        return;
      }

      gsap.set(".text-track", { autoAlpha: 0, y: 60, scale: 0.85, filter: "blur(20px)", rotationX: -20 });
      gsap.set(".text-days", { autoAlpha: 1, clipPath: "inset(0 100% 0 0)" });
      gsap.set(".main-card", { y: window.innerHeight + 200, autoAlpha: 1 });
      gsap.set([".card-left-text", ".card-right-text", ".mockup-scroll-wrapper", ".floating-badge", ".phone-widget"], { autoAlpha: 0 });
      gsap.set(".cta-wrapper", { autoAlpha: 0, scale: 0.8, filter: "blur(30px)" });

      gsap
        .timeline({ delay: 0.3 })
        .to(".text-track", { duration: 1.8, autoAlpha: 1, y: 0, scale: 1, filter: "blur(0px)", rotationX: 0, ease: "expo.out" })
        // Clearing the clip afterwards lets the text's soft shadow show in full, not cut into a box.
        .to(".text-days", { duration: 1.4, clipPath: "inset(0 0% 0 0)", ease: "power4.inOut", clearProps: "clipPath" }, "-=1.0");

      gsap
        .timeline({
          scrollTrigger: { trigger: containerRef.current, start: "top top", end: "+=7000", pin: true, scrub: 1, anticipatePin: 1 },
        })
        .to([".hero-text-wrapper", ".bg-grid-theme"], { scale: 1.15, filter: "blur(20px)", opacity: 0.2, ease: "power2.inOut", duration: 2 }, 0)
        .to(".main-card", { y: 0, ease: "power3.inOut", duration: 2 }, 0)
        .to(".main-card", { width: "100%", height: "100%", borderRadius: "0px", ease: "power3.inOut", duration: 1.5 })
        .fromTo(
          ".mockup-scroll-wrapper",
          { y: 300, z: -500, rotationX: 50, rotationY: -30, autoAlpha: 0, scale: 0.6 },
          { y: 0, z: 0, rotationX: 0, rotationY: 0, autoAlpha: 1, scale: 1, ease: "expo.out", duration: 2.5 },
          "-=0.8",
        )
        .fromTo(".phone-widget", { y: 40, autoAlpha: 0, scale: 0.95 }, { y: 0, autoAlpha: 1, scale: 1, stagger: 0.15, ease: "back.out(1.2)", duration: 1.5 }, "-=1.5")
        .to(".progress-ring", { strokeDashoffset: 60, duration: 2, ease: "power3.inOut" }, "-=1.2")
        .to(".counter-val", { innerHTML: metricValue, snap: { innerHTML: 1 }, duration: 2, ease: "expo.out" }, "-=2.0")
        .fromTo(
          ".floating-badge",
          { y: 100, autoAlpha: 0, scale: 0.7, rotationZ: -10 },
          { y: 0, autoAlpha: 1, scale: 1, rotationZ: 0, ease: "back.out(1.5)", duration: 1.5, stagger: 0.2 },
          "-=2.0",
        )
        .fromTo(".card-left-text", { x: -50, autoAlpha: 0 }, { x: 0, autoAlpha: 1, ease: "power4.out", duration: 1.5 }, "-=1.5")
        .fromTo(".card-right-text", { x: 50, autoAlpha: 0, scale: 0.8 }, { x: 0, autoAlpha: 1, scale: 1, ease: "expo.out", duration: 1.5 }, "<")
        .to({}, { duration: 2.5 })
        .set(".hero-text-wrapper", { autoAlpha: 0 })
        .set(".cta-wrapper", { autoAlpha: 1 })
        .to({}, { duration: 1.5 })
        .to([".mockup-scroll-wrapper", ".floating-badge", ".card-left-text", ".card-right-text"], {
          scale: 0.9, y: -40, z: -200, autoAlpha: 0, ease: "power3.in", duration: 1.2, stagger: 0.05,
        })
        .to(
          ".main-card",
          { width: isMobile ? "92vw" : "85vw", height: isMobile ? "92vh" : "85vh", borderRadius: isMobile ? "32px" : "40px", ease: "expo.inOut", duration: 1.8 },
          "pullback",
        )
        .to(".cta-wrapper", { scale: 1, filter: "blur(0px)", ease: "expo.inOut", duration: 1.8 }, "pullback")
        .to(".main-card", { y: -window.innerHeight - 300, ease: "power3.in", duration: 1.5 });
    }, containerRef);

    return () => ctx.revert();
  }, [metricValue]);

  return (
    <div
      ref={containerRef}
      className={cn("relative flex h-screen w-full items-center justify-center overflow-hidden bg-background font-sans text-foreground antialiased", className)}
      style={{ perspective: "1500px" }}
      {...props}
    >
      <style dangerouslySetInnerHTML={{ __html: INJECTED_STYLES }} />
      <div className="film-grain" aria-hidden="true" />
      <div className="bg-grid-theme pointer-events-none absolute inset-0 z-0 opacity-50" aria-hidden="true" />

      {/* Behind: the two headline lines */}
      <div className="hero-text-wrapper absolute z-10 flex w-full flex-col items-center justify-center px-4 text-center will-change-transform">
        <h1 className="flex flex-col items-center">
          <span className="text-track gsap-reveal text-3d-matte mb-2 block text-[clamp(2.25rem,9.5vw,6rem)] leading-[1.05] font-bold tracking-tight">{tagline1}</span>
          <span className="text-days gsap-reveal text-silver-matte block text-[clamp(2.25rem,9.5vw,6rem)] leading-[1.05] font-extrabold tracking-tighter">{tagline2}</span>
        </h1>
      </div>

      {/* Behind, later: the call to action */}
      <div className="cta-wrapper gsap-reveal pointer-events-auto absolute z-10 flex w-full flex-col items-center justify-center px-4 text-center will-change-transform">
        <h2 className="text-silver-matte mb-5 text-[clamp(2rem,8vw,4.5rem)] leading-[1.08] font-bold tracking-tight md:mb-6">{ctaHeading}</h2>
        {ctaDescription && <p className="mx-auto mb-8 max-w-xl text-base leading-relaxed font-light text-muted-foreground md:mb-12 md:text-xl">{ctaDescription}</p>}
        {ctaActions && <div className="flex flex-row flex-wrap justify-center gap-3 sm:gap-6">{ctaActions}</div>}
      </div>

      {/* In front: the deep blue card */}
      <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center" style={{ perspective: "1500px" }}>
        <div
          ref={mainCardRef}
          className="main-card premium-depth-card gsap-reveal pointer-events-auto relative flex h-[92vh] w-[92vw] items-center justify-center overflow-hidden rounded-[32px] md:h-[85vh] md:w-[85vw] md:rounded-[40px]"
        >
          <div className="card-sheen" aria-hidden="true" />

          <div className={cn("relative z-10 mx-auto flex h-full w-full max-w-7xl flex-col items-center justify-evenly px-4 py-6 lg:grid lg:grid-cols-3 lg:gap-8 lg:px-12 lg:py-0", contentClassName)}>
            {/* Top on phones, right on wide screens: the brand */}
            <div className="card-right-text gsap-reveal z-20 order-1 flex w-full justify-center lg:order-3 lg:justify-end">
              <h2 className="text-card-silver-matte text-5xl font-black tracking-tighter uppercase md:text-7xl lg:text-[4.5rem] xl:text-[5.5rem]">{brandName}</h2>
            </div>

            {/* Middle: the phone */}
            <div className="mockup-scroll-wrapper relative z-10 order-2 flex h-[310px] w-full items-center justify-center md:h-[500px] lg:h-[600px]" style={{ perspective: "1000px" }}>
              <div className="relative flex h-full w-full scale-[0.55] items-center justify-center md:scale-85 lg:scale-100">
                <div ref={mockupRef} className="iphone-bezel relative flex h-[580px] w-[280px] flex-col rounded-[3rem] will-change-transform">
                  {/* Hardware buttons */}
                  <div className="hardware-btn absolute top-[120px] -left-[3px] z-0 h-[25px] w-[3px] rounded-l-md" aria-hidden="true" />
                  <div className="hardware-btn absolute top-[160px] -left-[3px] z-0 h-[45px] w-[3px] rounded-l-md" aria-hidden="true" />
                  <div className="hardware-btn absolute top-[220px] -left-[3px] z-0 h-[45px] w-[3px] rounded-l-md" aria-hidden="true" />
                  <div className="hardware-btn absolute top-[170px] -right-[3px] z-0 h-[70px] w-[3px] scale-x-[-1] rounded-r-md" aria-hidden="true" />

                  {/* The screen */}
                  <div className="absolute inset-[7px] z-10 overflow-hidden rounded-[2.5rem] bg-[#050914] text-white">
                    <div className="screen-glare pointer-events-none absolute inset-0 z-40" aria-hidden="true" />
                    <div className="absolute top-[10px] left-1/2 z-50 h-[26px] w-[90px] -translate-x-1/2 rounded-full bg-black" aria-hidden="true" />
                    <div className="relative flex h-full w-full flex-col px-4 pt-12 pb-6">
                      {phoneHeader && <div className="phone-widget mb-4">{phoneHeader}</div>}
                      {/* The ring and the counting number */}
                      <div className="phone-widget relative mx-auto mb-5 flex size-40 items-center justify-center">
                        <svg className="absolute inset-0 size-full" viewBox="0 0 160 160" aria-hidden="true">
                          <defs>
                            <linearGradient id="hero-ring" x1="0" y1="0" x2="1" y2="1">
                              <stop offset="0" stopColor="#38bdf8" />
                              <stop offset="1" stopColor="#a78bfa" />
                            </linearGradient>
                          </defs>
                          <circle cx="80" cy="80" r="64" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" />
                          <circle className="progress-ring" cx="80" cy="80" r="64" fill="none" stroke="url(#hero-ring)" strokeWidth="10" />
                        </svg>
                        <div className="text-center">
                          <span className="counter-val block text-4xl font-extrabold tracking-tighter tabular-nums">0</span>
                          <span className="mx-auto mt-1 block max-w-[6.5rem] text-[9px] leading-snug font-bold tracking-[0.2em] text-blue-200/50 uppercase">{metricLabel}</span>
                        </div>
                      </div>
                      <div className="flex flex-col gap-2.5">{phoneWidgets}</div>
                    </div>
                  </div>
                </div>

                {badges}
              </div>
            </div>

            {/* Bottom on phones, left on wide screens: the message */}
            <div className="card-left-text gsap-reveal z-20 order-3 flex w-full flex-col justify-center px-2 text-center lg:order-1 lg:px-0 lg:text-left">
              <h3 className="mb-2 text-2xl font-bold tracking-tight text-white md:text-3xl lg:mb-5 lg:text-4xl">{cardHeading}</h3>
              <p className="mx-auto line-clamp-4 max-w-md text-sm leading-relaxed text-blue-100/70 md:text-base lg:mx-0 lg:line-clamp-none lg:max-w-none lg:text-lg">{cardDescription}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
