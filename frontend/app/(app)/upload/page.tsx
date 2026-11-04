"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Uploading now happens on Home; old links land there. */
export default function UploadPage() {
  const router = useRouter();
  useEffect(() => router.replace("/documents"), [router]);
  return null;
}
