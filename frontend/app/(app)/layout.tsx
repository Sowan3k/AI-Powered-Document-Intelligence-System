import { Suspense, type ReactNode } from "react";

import { AuthGate } from "@/components/auth-gate";

// The gate reads the URL and the browser's token, so it renders after the
// static shell (Suspense), never during prerendering.
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={null}>
      <AuthGate>{children}</AuthGate>
    </Suspense>
  );
}
