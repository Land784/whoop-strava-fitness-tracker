"use client";

/**
 * Server state vs mutations:
 *   - useQuery READS server state (workouts, recovery) and caches it.
 *   - useMutation CHANGES server state (triggering a sync). After it succeeds we
 *     invalidateQueries so React Query refetches the now-stale lists instead of
 *     us hand-patching local state.
 */

import { recoveryApi } from "@/api/recovery";
import { workoutsApi } from "@/api/workouts";
import { formatDuration, formatMiles, formatPace } from "@/lib/format";
import Sidebar from "@/components/layout/Sidebar";
import { useAuth } from "@/contexts/AuthContext";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

function recoveryTone(score: number | null | undefined) {
  if (score == null) return { color: "#334155", label: "No data", text: "text-slate-500" };
  if (score >= 67) return { color: "#34D399", label: "Green · ready to perform", text: "text-emerald-400" };
  if (score >= 34) return { color: "#FBBF24", label: "Yellow · train with care", text: "text-amber-400" };
  return { color: "#FB7185", label: "Red · prioritise recovery", text: "text-rose-400" };
}

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const { data: workouts = [] } = useQuery({
    queryKey: ["workouts"],
    queryFn: () => workoutsApi.list(0, 10),
    enabled: !!user,
  });

  const { data: recovery = [] } = useQuery({
    queryKey: ["recovery"],
    queryFn: () => recoveryApi.list(0, 7),
    enabled: !!user,
  });

  const sync = useMutation({
    mutationFn: () => workoutsApi.sync(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workouts"] });
      queryClient.invalidateQueries({ queryKey: ["recovery"] });
    },
  });

  const latest = recovery[0];
  const score = latest?.whoop_recovery_score ?? null;
  const tone = recoveryTone(score);
  const ringPct = score ?? 0;

  if (loading) {
    return (
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 p-8 flex items-center justify-center">
          <p className="text-slate-500">Loading…</p>
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 max-w-6xl">
        <header className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-display text-2xl font-bold text-white">Dashboard</h1>
            <p className="text-slate-500 text-sm mt-0.5">Welcome back, {user?.email}</p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <button
              onClick={() => sync.mutate()}
              disabled={sync.isPending}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-400 text-[#04130C] font-semibold text-sm hover:bg-emerald-300 transition-colors duration-200 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <svg
                className={`w-4 h-4 ${sync.isPending ? "animate-spin" : ""}`}
                viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}
                strokeLinecap="round" strokeLinejoin="round"
              >
                <path d="M21 12a9 9 0 1 1-3-6.7L21 8" />
                <path d="M21 3v5h-5" />
              </svg>
              {sync.isPending ? "Syncing…" : "Sync now"}
            </button>
            {sync.isError && <p className="text-xs text-rose-400">Sync failed — try again</p>}
            {sync.isSuccess && !sync.isPending && (
              <p className="text-xs text-emerald-400">Synced</p>
            )}
          </div>
        </header>

        {/* Recovery hero + key vitals */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-5">
          <div className="bg-panel rounded-2xl border border-line p-6 flex items-center gap-6">
            <div
              className="h-28 w-28 rounded-full grid place-items-center shrink-0"
              style={{ background: `conic-gradient(${tone.color} ${ringPct}%, rgba(255,255,255,0.06) ${ringPct}% 100%)` }}
            >
              <div className="h-[88px] w-[88px] rounded-full bg-panel grid place-items-center">
                <div className="text-center">
                  <p className={`font-display text-3xl font-bold leading-none ${tone.text} ${score != null ? "glow-recovery" : ""}`}>
                    {score ?? "—"}
                  </p>
                  <p className="text-[10px] uppercase tracking-widest text-slate-500 mt-1">Recovery</p>
                </div>
              </div>
            </div>
            <div>
              <p className={`text-sm font-semibold mb-1 ${tone.text}`}>{tone.label}</p>
              <p className="text-xs text-slate-500 leading-relaxed max-w-[200px]">
                {score != null
                  ? "Based on your latest WHOOP recovery score."
                  : "Connect WHOOP and sync to see your daily recovery here."}
              </p>
            </div>
          </div>

          <div className="bg-panel rounded-2xl border border-line p-5">
            <p className="text-[11px] uppercase tracking-widest text-slate-500">HRV</p>
            <p className="font-display text-3xl font-bold mt-2 text-slate-100">
              {latest?.hrv_ms?.toFixed(0) ?? "—"}
              {latest?.hrv_ms != null && <span className="text-base text-slate-500 font-normal ml-1">ms</span>}
            </p>
          </div>

          <div className="bg-panel rounded-2xl border border-line p-5">
            <p className="text-[11px] uppercase tracking-widest text-slate-500">Resting HR</p>
            <p className="font-display text-3xl font-bold mt-2 text-rose-400">
              {latest?.resting_hr ?? "—"}
              {latest?.resting_hr != null && <span className="text-base text-slate-500 font-normal ml-1">bpm</span>}
            </p>
          </div>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Recent workouts */}
          <section className="lg:col-span-2 bg-panel rounded-2xl border border-line p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display font-semibold text-sm text-slate-200">Recent workouts</h2>
              <span className="text-xs text-slate-500">{workouts.length} shown</span>
            </div>
            {workouts.length === 0 ? (
              <p className="text-slate-500 text-sm py-6 text-center">
                No workouts yet. Connect Strava in{" "}
                <span className="text-emerald-400">Settings</span> and hit Sync.
              </p>
            ) : (
              <div className="divide-y divide-line">
                {workouts.map((w) => (
                  <div key={w.id} className="flex items-center justify-between py-3.5">
                    <div className="flex items-center gap-3">
                      <div className="h-9 w-9 rounded-lg bg-sky-400/10 grid place-items-center">
                        <svg className="w-4 h-4 text-sky-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                          <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />
                        </svg>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-slate-100">{w.type ?? "Workout"}</p>
                        <p className="text-xs text-slate-500">
                          {w.date ?? "—"}
                          {w.duration_seconds != null && ` · ${formatDuration(w.duration_seconds)}`}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-display text-sm font-semibold text-slate-100">
                        {formatMiles(w.distance_meters)}
                      </p>
                      <p className="text-xs text-slate-500">
                        {formatPace(w.distance_meters, w.duration_seconds)}
                        {w.avg_hr ? ` · ${w.avg_hr} bpm` : ""}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Side column: sleep + AI teaser */}
          <section className="space-y-5">
            <div className="bg-panel rounded-2xl border border-line p-5">
              <p className="text-[11px] uppercase tracking-widest text-slate-500">Sleep score</p>
              <p className="font-display text-3xl font-bold mt-2 text-sky-400">
                {latest?.sleep_score?.toFixed(0) ?? "—"}
                {latest?.sleep_score != null && <span className="text-base text-slate-500 font-normal ml-1">%</span>}
              </p>
            </div>
            <div className="rounded-2xl border border-line bg-gradient-to-br from-emerald-400/10 to-sky-400/10 p-5">
              <p className="text-xs font-semibold text-slate-200 mb-1">AI Coach</p>
              <p className="text-xs text-slate-400 leading-relaxed">
                Ask for a training plan or recovery insight on the{" "}
                <span className="text-emerald-400">AI Insights</span> page.
              </p>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
