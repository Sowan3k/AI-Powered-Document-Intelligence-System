"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { LoginScreen } from "@/components/login-screen";
import { readToken } from "@/lib/api";

/** Signed in: straight to Home. Otherwise: sign in right here, no extra page. */
export default function Start() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    if (readToken()) router.replace("/documents");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    else setChecked(true);
  }, [router]);
  if (!checked) return null;
  return <LoginScreen />;
}
