"use client";

import { authApi } from "@/api/auth";
import Sidebar from "@/components/layout/Sidebar";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function SettingsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const { data: connections, isLoading } = useQuery({
    queryKey: ["connections"],
    queryFn: () => authApi.getConnections(),
    enabled: !!user,
  });

  async function handleConnectStrava() {
    setError("");
    setConnecting(true);
    try {
      // 1) ask our backend for the authorize URL (carries our signed `state`)
      const { authorization_url } = await authApi.getStravaAuthorizeUrl();
      // 2) hand the *browser* over to Strava — this is a navigation, not a fetch
      window.location.href = authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start Strava connection");
      setConnecting(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 max-w-3xl">
        <header className="mb-8">
          <h1 className="font-display text-2xl font-bold text-white">Settings</h1>
          <p className="text-slate-500 text-sm mt-0.5">Connect your data sources</p>
        </header>

        <section>
          <h2 className="font-display text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4">
            Connections
          </h2>

          {error && (
            <div className="mb-4 bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          <div className="space-y-3">
            {/* Strava */}
            <ProviderCard
              name="Strava"
              description="Activities, distance, heart rate"
              logo={
                <svg className="w-8 h-8" viewBox="0 0 24 24" fill="#FC4C02" aria-hidden="true">
                  <path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169" />
                </svg>
              }
              connected={connections?.strava_connected}
              loading={isLoading}
              action={
                connections?.strava_connected ? (
                  <span className="px-3 py-1.5 rounded-lg bg-white/5 text-slate-300 text-xs font-medium border border-line">
                    Manage
                  </span>
                ) : (
                  <button
                    onClick={handleConnectStrava}
                    disabled={connecting}
                    className="px-4 py-1.5 rounded-lg bg-emerald-400 text-[#04130C] text-sm font-semibold hover:bg-emerald-300 transition-colors duration-200 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {connecting ? "Redirecting…" : "Connect"}
                  </button>
                )
              }
            />

            {/* WHOOP — OAuth not wired yet (deferred to its own phase) */}
            <ProviderCard
              name="WHOOP"
              description="Recovery, HRV, sleep"
              logo={
                <div className="w-8 h-8 rounded-full border-2 border-sky-400 grid place-items-center" aria-hidden="true">
                  <div className="w-3 h-3 rounded-full bg-sky-400" />
                </div>
              }
              connected={connections?.whoop_connected}
              loading={isLoading}
              action={
                connections?.whoop_connected ? (
                  <span className="px-3 py-1.5 rounded-lg bg-white/5 text-slate-300 text-xs font-medium border border-line">
                    Manage
                  </span>
                ) : (
                  <span className="px-3 py-1.5 rounded-lg bg-white/5 text-slate-500 text-xs font-medium border border-line">
                    Coming soon
                  </span>
                )
              }
            />
          </div>
        </section>
      </main>
    </div>
  );
}

function ProviderCard({
  name,
  description,
  logo,
  connected,
  loading,
  action,
}: {
  name: string;
  description: string;
  logo: React.ReactNode;
  connected: boolean | undefined;
  loading: boolean;
  action: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between rounded-2xl bg-panel border border-line p-4">
      <div className="flex items-center gap-4">
        {logo}
        <div>
          <p className="text-sm font-semibold text-slate-100">{name}</p>
          {loading ? (
            <span className="inline-block mt-1 h-3 w-20 rounded bg-white/5 animate-pulse" />
          ) : connected ? (
            <p className="text-xs text-emerald-400 flex items-center gap-1.5 mt-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
              Connected
            </p>
          ) : (
            <p className="text-xs text-slate-500 mt-0.5">{description}</p>
          )}
        </div>
      </div>
      {action}
    </div>
  );
}
