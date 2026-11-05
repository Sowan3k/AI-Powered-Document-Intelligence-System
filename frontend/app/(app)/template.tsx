import type { ReactNode } from "react";

import { PageTransition } from "@/components/page-transition";

// A template gets a new key on each navigation between tabs, so the page
// inside it can slide out and the next one in (D73).
export default function Template({ children }: { children: ReactNode }) {
  return <PageTransition>{children}</PageTransition>;
}
