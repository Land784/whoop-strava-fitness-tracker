"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

function CallbackInner() {
  const params = useSearchParams();
  const router = useRouter();

  const provider = params.get("provider") ?? "account";
  const ok = params.get("status") === "connected";
  const providerLabel = provider.charAt(0).toUpperCase() + provider.slice(1);

  // On success, bounce back to Settings after a beat so the user sees the
  // confirmation. Settings refetches connection status on mount, so it'll show
  // the provider as Connected.
  useEffect(() => {
    if (!ok) return;
    const t = setTimeout(() => router.replace("/settings"), 2000);
    return () => clearTimeout(t);
  }, [ok, router]);

  return (
    <div className="min-h-screen bg-ink flex items-center justify-center px-4">
      <div className="w-full max-w-sm bg-panel border border-line rounded-2xl p-8 text-center">
        <div
          className={`mx-auto mb-5 h-14 w-14 rounded-full grid place-items-center ${
            ok ? "bg-emerald-400/15" : "bg-rose-500/15"
          }`}
        >
          {ok ? (
            <svg className="w-7 h-7 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6 9 17l-5-5" />
            </svg>
          ) : (
            <svg className="w-7 h-7 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          )}
        </div>

        <h1 className="font-display text-xl font-bold text-white">
          {ok ? `${providerLabel} connected` : "Connection failed"}
        </h1>
        <p className="text-sm text-slate-500 mt-2">
          {ok
            ? "We're pulling in your data now. Taking you back to Settings…"
            : `We couldn't connect ${providerLabel}. The link may have expired — please try again.`}
        </p>

        <Link
          href="/settings"
          className="inline-block mt-6 px-4 py-2 rounded-lg bg-emerald-400 text-[#04130C] text-sm font-semibold hover:bg-emerald-300 transition-colors duration-200 cursor-pointer"
        >
          {ok ? "Continue" : "Back to Settings"}
        </Link>
      </div>
    </div>
  );
}

export default function OAuthCallbackPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-ink" />}>
      <CallbackInner />
    </Suspense>
  );
}
