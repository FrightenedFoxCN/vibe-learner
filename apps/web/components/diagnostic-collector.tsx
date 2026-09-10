"use client";
import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { flushDiagnostics, registerDiagnosticPage } from "../lib/diagnostics";
import { getAiBaseUrl } from "../lib/runtime-config";

/** Collection lifetime is the app lifetime, independent of the Debug Overlay. */
export function DiagnosticCollector() {
  const pathname = usePathname();
  useEffect(() => {
    const page = registerDiagnosticPage();
    return page.dispose;
  }, [pathname]);
  useEffect(() => {
    const flush = () => { void flushDiagnostics(getAiBaseUrl()); };
    const timer = window.setInterval(flush, 2000);
    window.addEventListener("online", flush);
    return () => { window.clearInterval(timer); window.removeEventListener("online", flush); };
  }, []);
  return null;
}
