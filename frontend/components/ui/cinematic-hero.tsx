"use client";

// A scroll-driven landing hero: two lines of headline, then a deep card rises,
// fills the screen, and an iPhone mockup flies in with widgets and floating
// badges, before a call to action. Adapted from a shared shadcn-style
// component (D74): the content comes in through props, the phone screen and
// badges are slots, and people who ask for reduced motion get a still layout.
//
// Built to stay smooth on phones (D75): the stage sticks with CSS
// position: sticky instead of a JavaScript pin, and the scroll animates only
// transform and opacity, so no frame needs a new layout or a blur.

import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import React, { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger);
  // Phone browsers resize the viewport as their toolbars slide; ignore that,
  // the stage is sized in svh and does not change.
  ScrollTrigger.config({ ignoreMobileResize: true });
}

const INJECTED_STYLES = `
  .gsap-reveal { visibility: hidden; }

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
      background: linear-gradient(145deg, #1b2d47 0%, #0a111c 100%);
      box-shadow:
          0 40px 100px -20px rgba(0, 0, 0, 0.9),
          0 20px 40px -20px rgba(0, 0, 0, 0.8),
          inset 0 1px 2px rgba(255, 255, 255, 0.2),
          inset 0 -2px 4px rgba(0, 0, 0, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.04);
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

  /* No backdrop blur: behind a badge is a smooth gradient, so blur would cost every frame and show nothing. */
  .floating-ui-badge {
      background: linear-gradient(135deg, rgba(40, 56, 110, 0.92) 0%, rgba(20, 28, 58, 0.9) 100%);
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

export interface CinematicHeroProps extends React.HTMLAttributes<HTMLElement> {
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
  const sectionRef = useRef<HTMLElement>(null);
  const mainCardRef = useRef<HTMLDivElement>(null);
  const mockupRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef<number>(0);

  // 1. Mouse lighting and phone tilt, on a mouse only, once per frame at most.
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    const handleMouseMove = (e: MouseEvent) => {
      cancelAnimationFrame(requestRef.current);
      requestRef.current = requestAnimationFrame(() => {
        if (!mainCardRef.current || !mockupRef.current) return;
        const rect = mainCardRef.current.getBoundingClientRect();
        if (rect.bottom < 0 || rect.top > window.innerHeight) return;
        mainCardRef.current.style.setProperty("--mouse-x", `${e.clientX - rect.left}px`);
        mainCardRef.current.style.setProperty("--mouse-y", `${e.clientY - rect.top}px`);
        const xVal = (e.clientX / window.innerWidth - 0.5) * 2;
        const yVal = (e.clientY / window.innerHeight - 0.5) * 2;
        gsap.to(mockupRef.current, { rotationY: xVal * 10, rotationX: -yVal * 10, ease: "power3.out", duration: 1.2 });
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
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const content = [".mockup-scroll-wrapper", ".card-left-text", ".card-right-text", ".floating-badge", ".phone-widget"];

    const ctx = gsap.context(() => {
      if (reduce) {
        gsap.set([".hero-text-wrapper", ".cta-wrapper"], { autoAlpha: 0 });
        gsap.set(".main-card", { autoAlpha: 1 });
        gsap.set(content, { autoAlpha: 1 });
        gsap.set(".progress-ring", { strokeDashoffset: 60 });
        gsap.set(".counter-val", { innerHTML: metricValue });
        return;
      }

      // At rest the card peeks up from the bottom edge: there is more below.
      gsap.set(".main-card", { autoAlpha: 1, yPercent: 78, scale: 0.88 });
      gsap.set(content, { autoAlpha: 0 });
      gsap.set(".cta-wrapper", { autoAlpha: 0, scale: 0.94, y: 24 });
      gsap.set(".text-track", { autoAlpha: 0, y: 40, scale: 0.94 });
      gsap.set(".text-days", { autoAlpha: 1, clipPath: "inset(0 100% 0 0)" });

      gsap
        .timeline({ delay: 0.2 })
        .to(".text-track", { duration: 1.2, autoAlpha: 1, y: 0, scale: 1, ease: "expo.out" })
        // Clearing the clip afterwards lets the text's soft shadow show in full, not cut into a box.
        .to(".text-days", { duration: 1.1, clipPath: "inset(0 0% 0 0)", ease: "power4.inOut", clearProps: "clipPath" }, "-=0.8")
        .fromTo(".main-card", { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.8, ease: "power1.out" }, "-=0.6");

      // The content rides inside the card: it arrives with the card and leaves
      // with it, so the card is never an empty blue screen.
      gsap
        .timeline({
          defaults: { ease: "power2.out" },
          scrollTrigger: { trigger: sectionRef.current, start: "top top", end: "bottom bottom", scrub: 0.4 },
        })
        .to(".hero-text-wrapper", { autoAlpha: 0, scale: 0.92, duration: 1.2, ease: "power1.in" }, 0)
        .to(".bg-grid-theme", { autoAlpha: 0, duration: 1.2 }, 0)
        .to(".main-card", { yPercent: 0, scale: 1, duration: 1.6, ease: "power2.inOut" }, 0)
        .fromTo(
          ".mockup-scroll-wrapper",
          { y: 120, rotationX: 28, rotationY: -14, scale: 0.82, autoAlpha: 0 },
          { y: 0, rotationX: 0, rotationY: 0, scale: 1, autoAlpha: 1, duration: 1.7, ease: "power3.out" },
          0.2,
        )
        .fromTo(".card-right-text", { y: -20, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 1 }, 0.4)
        .fromTo(".card-left-text", { y: 24, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 1 }, 0.7)
        .fromTo(".phone-widget", { y: 18, autoAlpha: 0 }, { y: 0, autoAlpha: 1, stagger: 0.14, duration: 0.8 }, 0.8)
        .to(".progress-ring", { strokeDashoffset: 60, duration: 1.4 }, 1.0)
        .to(".counter-val", { innerHTML: metricValue, snap: { innerHTML: 1 }, duration: 1.4 }, 1.0)
        .fromTo(".floating-badge", { y: 30, autoAlpha: 0, scale: 0.88 }, { y: 0, autoAlpha: 1, scale: 1, stagger: 0.2, duration: 0.9, ease: "back.out(1.4)" }, 1.4)
        // A short rest with everything in view, then the card slides away with its content.
        .to(".main-card", { yPercent: -108, duration: 1.6, ease: "power2.in" }, 3.6)
        .to(".cta-wrapper", { autoAlpha: 1, scale: 1, y: 0, duration: 1 }, 4.4)
        .to({}, { duration: 0.4 });
    }, sectionRef);

    return () => ctx.revert();
  }, [metricValue]);

  return (
    <section
      ref={sectionRef}
      className={cn("relative h-[300svh] w-full motion-reduce:h-auto", className)}
      {...props}
    >
      <style dangerouslySetInnerHTML={{ __html: INJECTED_STYLES }} />
      <div
        className="sticky top-0 flex h-svh w-full items-center justify-center overflow-hidden bg-background font-sans text-foreground antialiased"
        style={{ perspective: "1500px" }}
      >
        <div className="bg-grid-theme pointer-events-none absolute inset-0 z-0 opacity-50" aria-hidden="true" />

        {/* Behind: the two headline lines */}
        <div className="hero-text-wrapper absolute z-10 flex w-full flex-col items-center justify-center px-4 pb-[18svh] text-center will-change-transform">
          <h1 className="flex flex-col items-center">
            <span className="text-track gsap-reveal text-3d-matte type-display mb-2 block text-[clamp(2.5rem,10.5vw,6.5rem)] leading-[1.02]">{tagline1}</span>
            <span className="text-days gsap-reveal text-silver-matte type-display block text-[clamp(2.5rem,10.5vw,6.5rem)] leading-[1.02]">{tagline2}</span>
          </h1>
        </div>

        {/* Behind, later: the call to action */}
        <div className="cta-wrapper gsap-reveal pointer-events-auto absolute z-10 flex w-full flex-col items-center justify-center px-4 text-center will-change-transform">
          <h2 className="text-silver-matte type-display mb-5 text-[clamp(2.25rem,9vw,5rem)] md:mb-6">{ctaHeading}</h2>
          {ctaDescription && <p className="mx-auto mb-8 max-w-xl text-base leading-relaxed font-light text-muted-foreground md:mb-12 md:text-xl">{ctaDescription}</p>}
          {ctaActions && <div className="flex flex-row flex-wrap justify-center gap-3 sm:gap-6">{ctaActions}</div>}
        </div>

        {/* In front: the deep blue card. It only moves and scales, so it never needs a new layout. */}
        <div
          ref={mainCardRef}
          className="main-card premium-depth-card gsap-reveal absolute inset-0 z-20 flex items-center justify-center overflow-hidden rounded-[28px] will-change-transform md:inset-3 md:rounded-[40px]"
        >
          <div className="card-sheen" aria-hidden="true" />

          <div className={cn("relative z-10 mx-auto flex h-full w-full max-w-7xl flex-col items-center justify-evenly px-4 py-6 lg:grid lg:grid-cols-3 lg:gap-8 lg:px-12 lg:py-0", contentClassName)}>
            {/* Top on phones, right on wide screens: the brand */}
            <div className="card-right-text gsap-reveal z-20 order-1 flex w-full justify-center lg:order-3 lg:justify-end">
              <h2 className="text-card-silver-matte type-display text-6xl tracking-normal uppercase md:text-8xl lg:text-[5rem] xl:text-[6rem]">{brandName}</h2>
            </div>

            {/* Middle: the phone */}
            <div className="mockup-scroll-wrapper gsap-reveal relative z-10 order-2 flex h-[310px] w-full items-center justify-center will-change-transform md:h-[500px] lg:h-[600px]" style={{ perspective: "1000px" }}>
              <div className="relative flex h-full w-full scale-[0.55] items-center justify-center md:scale-85 lg:scale-100">
                <div ref={mockupRef} className="iphone-bezel relative flex h-[580px] w-[280px] flex-col rounded-[3rem]">
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
                      {phoneHeader && <div className="phone-widget gsap-reveal mb-4">{phoneHeader}</div>}
                      {/* The ring and the counting number */}
                      <div className="phone-widget gsap-reveal relative mx-auto mb-5 flex size-40 items-center justify-center">
                        <svg className="absolute inset-0 size-full" viewBox="0 0 160 160" aria-hidden="true">
                          <defs>
                            <linearGradient id="hero-ring" x1="0" y1="0" x2="1" y2="1">
                              <stop offset="0" stopColor="#3dbe8b" />
                              <stop offset="1" stopColor="#d9a94e" />
                            </linearGradient>
                          </defs>
                          <circle cx="80" cy="80" r="64" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" />
                          <circle className="progress-ring" cx="80" cy="80" r="64" fill="none" stroke="url(#hero-ring)" strokeWidth="10" />
                        </svg>
                        <div className="text-center">
                          <span className="counter-val type-figure block text-5xl">0</span>
                          <span className="mx-auto mt-1 block max-w-[6.5rem] text-[9px] leading-snug font-bold tracking-[0.2em] text-[#ece6d9]/50 uppercase">{metricLabel}</span>
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
              <h3 className="type-display mb-2 text-3xl text-white md:text-4xl lg:mb-5 lg:text-5xl">{cardHeading}</h3>
              <p className="mx-auto line-clamp-4 max-w-md text-sm leading-relaxed text-[#ece6d9]/75 md:text-base lg:mx-0 lg:line-clamp-none lg:max-w-none lg:text-lg">{cardDescription}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
