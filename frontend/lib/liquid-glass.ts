"use client";

// Refraction for liquid glass (D76). A thick curved edge bends what is behind
// it. Chromium can run an SVG filter on an element's backdrop, so each glass
// element gets a displacement map shaped like its own rounded rectangle: zero
// in the middle, rising toward the rim, where the backdrop is pulled inward.
// Other browsers keep the clear glass from globals.css without the bending.

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
 * Red and green hold the x and y pull (128 is none). Inside a band along the
 * rim the pull rises smoothly to its full strength at the edge and points
 * inward, along the edge's normal, so the rim shows the backdrop squeezed
 * like the thick edge of a lens.
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
      if (depth < band) {
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
        const t = 1 - Math.max(depth, 0) / band;
        const m = t * t * (3 - 2 * t);
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
  /** How far the rim pulls, relative to the band width. */
  strength?: number;
};

/**
 * Returns a ref for a glass element. In Chromium it adds edge refraction,
 * rebuilt when the element changes size; elsewhere it does nothing.
 */
export function useLiquidGlass<T extends HTMLElement>({ blur = 2, strength = 1.3 }: Options = {}) {
  return useCallback(
    (el: T | null) => {
      if (!el || !canRefract()) return;
      const id = `lg-${Math.random().toString(36).slice(2, 10)}`;
      const filter = document.createElementNS(SVG_NS, "filter");
      filter.setAttribute("id", id);
      filter.setAttribute("filterUnits", "userSpaceOnUse");
      filter.setAttribute("primitiveUnits", "userSpaceOnUse");
      // The map holds plain numbers, not colours: keep it out of linear RGB.
      filter.setAttribute("color-interpolation-filters", "sRGB");
      const image = document.createElementNS(SVG_NS, "feImage");
      image.setAttribute("result", "map");
      image.setAttribute("preserveAspectRatio", "none");
      const displace = document.createElementNS(SVG_NS, "feDisplacementMap");
      displace.setAttribute("in", "SourceGraphic");
      displace.setAttribute("in2", "map");
      displace.setAttribute("xChannelSelector", "R");
      displace.setAttribute("yChannelSelector", "G");
      filter.append(image, displace);
      filterHost().appendChild(filter);

      let last = "";
      let frame = 0;
      const build = () => {
        const w = Math.round(el.offsetWidth);
        const h = Math.round(el.offsetHeight);
        if (w < 8 || h < 8) return;
        const r = Math.min(parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0, w / 2, h / 2);
        const key = `${w}x${h}:${r}`;
        if (key === last) return;
        last = key;
        const band = Math.max(6, Math.min(h * 0.4, w * 0.4, 20));
        for (const node of [filter, image]) {
          node.setAttribute("x", "0");
          node.setAttribute("y", "0");
          node.setAttribute("width", String(w));
          node.setAttribute("height", String(h));
        }
        image.setAttribute("href", displacementMap(w, h, r, band));
        displace.setAttribute("scale", String(Math.round(band * strength * 2)));
        el.style.backdropFilter = `url(#${id}) blur(${blur}px) saturate(185%) brightness(1.05)`;
      };
      const observer = new ResizeObserver(() => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(build);
      });
      observer.observe(el);
      build();

      return () => {
        observer.disconnect();
        cancelAnimationFrame(frame);
        filter.remove();
        el.style.backdropFilter = "";
      };
    },
    [blur, strength],
  );
}
