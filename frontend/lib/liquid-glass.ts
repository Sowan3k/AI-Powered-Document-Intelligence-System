"use client";

// Liquid glass (D76, D77). Each glass element behaves like a drop of water on
// the screen: a domed lens that magnifies what scrolls under it, squeezes it
// hard at the rim, and splits the colours slightly at the edge. Chromium can
// run an SVG filter on an element's backdrop, so each element gets a
// displacement map shaped like its own rounded rectangle. Other browsers keep
// the clear glass from globals.css without the bending.
//
// The light on the glass lives on small layers inside it (D78): glints around
// the rim that turn with the scroll (a CSS scroll-driven animation on the
// compositor) and with the phone's tilt or the mouse, and a sheen that slides
// with the tilt. Moving them is a transform only, so the glass and its text
// are not restyled or repainted. A press sends a ripple from the finger: a
// ring of light everywhere, and in Chromium a wave of distortion through the
// same filter.

import { useCallback } from "react";

const SVG_NS = "http://www.w3.org/2000/svg";
let host: SVGSVGElement | null = null;
let supported: boolean | null = null;

/**
 * Chromium only: it alone renders url() filters in backdrop-filter.
 * navigator.userAgentData exists only in Chromium browsers, including Chrome
 * on Android, and not in Safari or in iOS browsers (which all use WebKit).
 */
function canRefract(): boolean {
  if (supported === null) {
    supported =
      typeof navigator !== "undefined" &&
      "userAgentData" in navigator &&
      !window.matchMedia("(prefers-reduced-transparency: reduce)").matches;
  }
  return supported;
}

function filterHost(): SVGSVGElement {
  if (!host) {
    host = document.createElementNS(SVG_NS, "svg");
    host.setAttribute("aria-hidden", "true");
    host.setAttribute("width", "0");
    host.setAttribute("height", "0");
    host.style.position = "absolute";
    host.style.pointerEvents = "none";
    document.body.appendChild(host);
  }
  return host;
}

/**
 * Red and green hold the x and y pull (128 is none). The surface is a dome:
 * across a band almost as wide as half the element, its height follows a
 * circle, flat on top and steep at the rim. The pull follows the slope and
 * points inward, so the middle is gently magnified and the rim squeezes the
 * backdrop, as a drop of water does.
 */
function displacementMap(w: number, h: number, r: number, band: number): string {
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";
  const img = ctx.createImageData(w, h);
  const data = img.data;
  const hw = w / 2;
  const hh = h / 2;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const px = x + 0.5 - hw;
      const py = y + 0.5 - hh;
      const qx = Math.abs(px) - (hw - r);
      const qy = Math.abs(py) - (hh - r);
      const ox = Math.max(qx, 0);
      const oy = Math.max(qy, 0);
      const corner = Math.hypot(ox, oy);
      const depth = -(corner + Math.min(Math.max(qx, qy), 0) - r);
      let dx = 0;
      let dy = 0;
      if (depth < band && depth > -1) {
        let nx: number;
        let ny: number;
        if (qx > 0 && qy > 0 && corner > 0) {
          nx = ox / corner;
          ny = oy / corner;
        } else if (qx > qy) {
          nx = 1;
          ny = 0;
        } else {
          nx = 0;
          ny = 1;
        }
        nx *= px < 0 ? -1 : 1;
        ny *= py < 0 ? -1 : 1;
        const t = Math.min(Math.max(depth, 0) / band, 1);
        const sag = 1 - Math.sqrt(1 - (1 - t) * (1 - t));
        const m = 0.7 * sag + 0.3 * (1 - t);
        dx = -nx * m;
        dy = -ny * m;
      }
      const i = (y * w + x) * 4;
      data[i] = 128 + dx * 127;
      data[i + 1] = 128 + dy * 127;
      data[i + 2] = 128;
      data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL();
}

type Options = {
  /** Blur after the bend, in px. Small keeps the glass clear. */
  blur?: number;
  /** How far the rim pulls, relative to the dome's width. */
  strength?: number;
};

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

// ---- The light layers --------------------------------------------------------

type Live = { root: HTMLSpanElement; sheen: HTMLSpanElement; glint: HTMLSpanElement; w: number; h: number };

/** Adds the light layers to a glass element. They are not React's, so React leaves them alone. */
function addLayers(el: HTMLElement): Live & { remove: () => void } {
  const span = (cls: string) => {
    const node = document.createElement("span");
    node.className = cls;
    node.setAttribute("aria-hidden", "true");
    return node;
  };
  const root = span("lg-light");
  const sheen = span("lg-sheen");
  root.appendChild(sheen);
  const rim = span("lg-rim");
  const glint = span("lg-glint");
  rim.appendChild(glint);
  el.append(root, rim);
  el.classList.add("lg-live");
  return {
    root,
    sheen,
    glint,
    w: 0,
    h: 0,
    remove: () => {
      root.remove();
      rim.remove();
      el.classList.remove("lg-live");
    },
  };
}

/** The glint layer is a square that covers the glass at any angle, centred on it. */
function sizeGlint(live: Live, w: number, h: number) {
  live.w = w;
  live.h = h;
  const d = Math.ceil(Math.hypot(w, h));
  Object.assign(live.glint.style, { width: `${d}px`, height: `${d}px`, left: `${(w - d) / 2}px`, top: `${(h - d) / 2}px` });
}

// ---- The light source: the phone's tilt, or the mouse ----------------------

const lit = new Set<Live>();
const target = { a: 0, x: 0, y: 0 };
const now = { a: 0, x: 0, y: 0 };
let neutral: { beta: number; gamma: number } | null = null;
let lightFrame = 0;
let lightOn = false;

function paintLight() {
  let moving = false;
  for (const k of ["a", "x", "y"] as const) {
    now[k] += (target[k] - now[k]) * 0.12;
    if (Math.abs(target[k] - now[k]) > 0.01) moving = true;
  }
  // Transforms only: the compositor moves these layers without a repaint.
  for (const live of lit) {
    live.glint.style.transform = `rotate(${now.a.toFixed(2)}deg)`;
    live.sheen.style.transform = `translate3d(${(now.x * live.w * 0.3).toFixed(1)}px, ${(now.y * live.h * 0.4).toFixed(1)}px, 0)`;
  }
  lightFrame = moving ? requestAnimationFrame(paintLight) : 0;
}

/** dx and dy run from -1 to 1: where the light has moved, left-right and up-down. */
function aim(dx: number, dy: number) {
  target.a = dx * 40;
  target.x = dx;
  target.y = dy;
  if (!lightFrame) lightFrame = requestAnimationFrame(paintLight);
}

function onTilt(e: DeviceOrientationEvent) {
  if (e.beta === null || e.gamma === null) return;
  // The way the phone is held becomes neutral, and the neutral point drifts
  // slowly after the hand, so only a change of angle moves the light.
  if (!neutral) neutral = { beta: e.beta, gamma: e.gamma };
  neutral.beta += (e.beta - neutral.beta) * 0.01;
  neutral.gamma += (e.gamma - neutral.gamma) * 0.01;
  aim(clamp((e.gamma - neutral.gamma) / 25, -1, 1), clamp((e.beta - neutral.beta) / 25, -1, 1));
}

function onPointer(e: PointerEvent) {
  if (e.pointerType !== "mouse") return;
  aim((e.clientX / window.innerWidth - 0.5) * 2, (e.clientY / window.innerHeight - 0.5) * 2);
}

function followLight(live: Live): () => void {
  if (reducedMotion()) return () => {};
  lit.add(live);
  if (!lightOn) {
    lightOn = true;
    // Chrome on Android sends these without asking. iOS Safari needs a
    // permission prompt, which this page does not show, so it gets none.
    window.addEventListener("deviceorientation", onTilt, { passive: true });
    window.addEventListener("pointermove", onPointer, { passive: true });
  }
  return () => {
    lit.delete(live);
    if (lit.size === 0 && lightOn) {
      lightOn = false;
      window.removeEventListener("deviceorientation", onTilt);
      window.removeEventListener("pointermove", onPointer);
    }
  };
}

// ---- Ripples under the finger ----------------------------------------------

let ringUrl = "";

/**
 * A wave that pushes outward from the centre: a crest near the edge of the
 * circle and a smaller one behind it, nothing outside the circle (transparent,
 * which the filter turns into "no pull").
 */
function ringMap(): string {
  if (ringUrl) return ringUrl;
  const n = 160;
  const canvas = document.createElement("canvas");
  canvas.width = n;
  canvas.height = n;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";
  const img = ctx.createImageData(n, n);
  const data = img.data;
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const u = ((x + 0.5) / n) * 2 - 1;
      const v = ((y + 0.5) / n) * 2 - 1;
      const r = Math.hypot(u, v);
      const i = (y * n + x) * 4;
      if (r > 1) continue;
      const wave = clamp(Math.sin(r * Math.PI * 3) * Math.exp(-((r - 0.72) ** 2) / 0.06) * 1.4, -1, 1);
      const d = r > 0 ? wave / r : 0;
      data[i] = 128 + u * d * 127;
      data[i + 1] = 128 + v * d * 127;
      data[i + 2] = 128;
      data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  ringUrl = canvas.toDataURL();
  return ringUrl;
}

/** The ring of light, in every browser, on the light layer, so the glass does not repaint. */
function lightRipple(live: Live, x: number, y: number) {
  const el = live.root;
  el.style.setProperty("--lg-rx", `${x}px`);
  el.style.setProperty("--lg-ry", `${y}px`);
  const reach = Math.hypot(live.w, live.h) * 0.7;
  el.animate(
    [
      { "--lg-ripple": "0px", "--lg-ripple-a": "0.8" },
      { "--lg-ripple": `${reach}px`, "--lg-ripple-a": "0" },
    ],
    { duration: 700, easing: "cubic-bezier(0.2, 0.7, 0.2, 1)" },
  );
}

// ---- Refraction ------------------------------------------------------------

/** Keeps one colour channel of a displaced copy, so the three can be added back up. */
function channel(index: 0 | 1 | 2): string {
  const rows = [0, 1, 2].map((r) => (r === index ? [0, 1, 2].map((c) => (c === index ? 1 : 0)).join(" ") + " 0 0" : "0 0 0 0 0"));
  return `${rows.join(" ")} 0 0 0 1 0`;
}

function fe<K extends keyof SVGElementTagNameMap>(name: K, attrs: Record<string, string>): SVGElementTagNameMap[K] {
  const node = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

/**
 * Returns a ref for a glass element. Everywhere: light layers whose glints
 * turn with the scroll and the tilt or mouse, and a ring of light on a press.
 * In Chromium also: the dome refraction with its colour fringe, and the
 * ripple's wave of distortion. Elements marked .glass-still keep their light
 * still (the opening page animates its hero on scroll already).
 */
export function useLiquidGlass<T extends HTMLElement>({ blur = 1.5, strength = 0.85 }: Options = {}) {
  return useCallback(
    (el: T | null) => {
      if (!el) return;
      const live = addLayers(el);
      const stopLight = el.classList.contains("glass-still") ? () => {} : followLight(live);
      const refract = canRefract();
      const calm = reducedMotion();

      // The refraction filter, Chromium only.
      const id = `lg-${Math.random().toString(36).slice(2, 10)}`;
      const filter = fe("filter", {
        id,
        filterUnits: "userSpaceOnUse",
        primitiveUnits: "userSpaceOnUse",
        // The maps hold plain numbers, not colours: keep them out of linear RGB.
        "color-interpolation-filters": "sRGB",
      });
      const image = fe("feImage", { result: "map", preserveAspectRatio: "none" });
      filter.appendChild(image);
      // Red bends most and blue least, as in water, which leaves a thin colour fringe.
      const bends = ([1, 0.94, 0.88] as const).map((k, i) => {
        const displace = fe("feDisplacementMap", { in: "SourceGraphic", in2: "map", xChannelSelector: "R", yChannelSelector: "G", result: `d${i}` });
        const keep = fe("feColorMatrix", { in: `d${i}`, type: "matrix", values: channel(i as 0 | 1 | 2), result: `c${i}` });
        filter.append(displace, keep);
        return { displace, k };
      });
      filter.append(
        fe("feComposite", { in: "c0", in2: "c1", operator: "arithmetic", k2: "1", k3: "1", result: "rg" }),
        fe("feComposite", { in: "rg", in2: "c2", operator: "arithmetic", k2: "1", k3: "1" }),
      );
      // The ripple's own stage, put in front of the dome only while a ripple runs.
      const flat = fe("feFlood", { "flood-color": "rgb(128,128,128)", result: "flat" });
      const ring = fe("feImage", { result: "ring", preserveAspectRatio: "none" });
      const ringOnFlat = fe("feComposite", { in: "ring", in2: "flat", operator: "over", result: "rmap" });
      const wave = fe("feDisplacementMap", { in: "SourceGraphic", in2: "rmap", xChannelSelector: "R", yChannelSelector: "G", result: "rippled" });
      if (refract) filterHost().appendChild(filter);

      let last = "";
      let frame = 0;
      const build = () => {
        const w = Math.round(el.offsetWidth);
        const h = Math.round(el.offsetHeight);
        if (w < 8 || h < 8) return;
        if (w !== live.w || h !== live.h) sizeGlint(live, w, h);
        if (!refract) return;
        const r = Math.min(parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0, w / 2, h / 2);
        const key = `${w}x${h}:${r}`;
        if (key === last) return;
        last = key;
        // The dome spans almost half the short side, so the whole piece is curved.
        const band = Math.max(8, (Math.min(w, h) / 2) * 0.92);
        for (const node of [filter, image, flat]) {
          node.setAttribute("x", "0");
          node.setAttribute("y", "0");
          node.setAttribute("width", String(w));
          node.setAttribute("height", String(h));
        }
        image.setAttribute("href", displacementMap(w, h, r, band));
        for (const { displace, k } of bends) displace.setAttribute("scale", String(Math.round(band * strength * 2 * k)));
        el.style.backdropFilter = `url(#${id}) blur(${blur}px) saturate(185%) brightness(1.05)`;
      };
      const observer = new ResizeObserver(() => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(build);
      });
      observer.observe(el);
      build();

      // A press: light everywhere, and in Chromium a wave through the filter.
      let waveFrame = 0;
      const endWave = () => {
        cancelAnimationFrame(waveFrame);
        waveFrame = 0;
        for (const node of [flat, ring, ringOnFlat, wave]) node.remove();
        for (const { displace } of bends) displace.setAttribute("in", "SourceGraphic");
      };
      const onPress = (e: PointerEvent) => {
        if (calm) return;
        const box = el.getBoundingClientRect();
        const x = e.clientX - box.left;
        const y = e.clientY - box.top;
        lightRipple(live, x, y);
        if (!refract || !last) return;
        if (!ring.getAttribute("href")) ring.setAttribute("href", ringMap());
        if (!waveFrame) {
          filter.insertBefore(flat, bends[0].displace);
          filter.insertBefore(ring, bends[0].displace);
          filter.insertBefore(ringOnFlat, bends[0].displace);
          filter.insertBefore(wave, bends[0].displace);
          for (const { displace } of bends) displace.setAttribute("in", "rippled");
        }
        cancelAnimationFrame(waveFrame);
        const reach = Math.hypot(box.width, box.height) * 0.75;
        const start = performance.now();
        const step = (t: number) => {
          // A frame's timestamp can be a little before the press was handled.
          const p = clamp((t - start) / 650, 0, 1);
          const grow = 1 - (1 - p) ** 3;
          const size = 18 + grow * reach * 2;
          ring.setAttribute("x", String(x - size / 2));
          ring.setAttribute("y", String(y - size / 2));
          ring.setAttribute("width", String(size));
          ring.setAttribute("height", String(size));
          wave.setAttribute("scale", String(34 * (1 - p) ** 1.5));
          if (p < 1) waveFrame = requestAnimationFrame(step);
          else endWave();
        };
        waveFrame = requestAnimationFrame(step);
      };
      el.addEventListener("pointerdown", onPress, { passive: true });

      return () => {
        stopLight();
        el.removeEventListener("pointerdown", onPress);
        endWave();
        observer.disconnect();
        live.remove();
        cancelAnimationFrame(frame);
        filter.remove();
        el.style.backdropFilter = "";
      };
    },
    [blur, strength],
  );
}
