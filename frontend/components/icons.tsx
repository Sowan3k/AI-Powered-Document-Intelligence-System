// Small inline icons (no icon library). Each takes a className for size and color.
type P = { className?: string };
const base = "fill-none stroke-current stroke-2 [stroke-linecap:round] [stroke-linejoin:round]";

export const HomeIcon = ({ className = "size-5" }: P) => (
  <svg viewBox="0 0 24 24" className={`${base} ${className}`} aria-hidden><path d="M3 11l9-7 9 7" /><path d="M5 10v10h14V10" /></svg>
);
export const ReviewIcon = ({ className = "size-5" }: P) => (
  <svg viewBox="0 0 24 24" className={`${base} ${className}`} aria-hidden><path d="M9 11l2 2 4-4" /><rect x="4" y="3" width="16" height="18" rx="2" /></svg>
);
export const SearchIcon = ({ className = "size-5" }: P) => (
  <svg viewBox="0 0 24 24" className={`${base} ${className}`} aria-hidden><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
);
export const CompareIcon = ({ className = "size-5" }: P) => (
  <svg viewBox="0 0 24 24" className={`${base} ${className}`} aria-hidden><rect x="3" y="4" width="7" height="16" rx="1" /><rect x="14" y="4" width="7" height="16" rx="1" /><path d="M10 12h4" /></svg>
);
export const UploadIcon = ({ className = "size-5" }: P) => (
  <svg viewBox="0 0 24 24" className={`${base} ${className}`} aria-hidden><path d="M12 16V4" /><path d="M7 9l5-5 5 5" /><path d="M4 16v4h16v-4" /></svg>
);
export const FileIcon = ({ className = "size-5" }: P) => (
  <svg viewBox="0 0 24 24" className={`${base} ${className}`} aria-hidden><path d="M14 3H6v18h12V7z" /><path d="M14 3v4h4" /></svg>
);
export const ReadIcon = ({ className = "size-5" }: P) => (
  <svg viewBox="0 0 24 24" className={`${base} ${className}`} aria-hidden><path d="M4 6h16M4 12h10M4 18h7" /></svg>
);
export const SparkIcon = ({ className = "size-5" }: P) => (
  <svg viewBox="0 0 24 24" className={`${base} ${className}`} aria-hidden><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /></svg>
);
export const ShieldIcon = ({ className = "size-5" }: P) => (
  <svg viewBox="0 0 24 24" className={`${base} ${className}`} aria-hidden><path d="M12 3l8 3v6c0 4.5-3.5 8-8 9-4.5-1-8-4.5-8-9V6z" /><path d="M9 12l2 2 4-4" /></svg>
);
export const CheckIcon = ({ className = "size-5" }: P) => (
  <svg viewBox="0 0 24 24" className={`${base} ${className}`} aria-hidden><path d="M5 12l5 5 9-10" /></svg>
);
export const AlertIcon = ({ className = "size-5" }: P) => (
  <svg viewBox="0 0 24 24" className={`${base} ${className}`} aria-hidden><path d="M12 3l10 18H2z" /><path d="M12 10v4M12 17.5v.5" /></svg>
);
export const ChevronIcon = ({ className = "size-4" }: P) => (
  <svg viewBox="0 0 24 24" className={`${base} ${className}`} aria-hidden><path d="M6 15l6-6 6 6" /></svg>
);
