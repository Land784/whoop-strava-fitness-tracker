"use client";

/**
 * Why useQuery here instead of useState + useEffect?
 *
 * useQuery handles the full server-state lifecycle: loading, error, caching,
 * and background refetches. The `enabled: !!user` option means the query
 * won't fire until the user is authenticated — no extra if-guards needed.
 * When this component mounts again (e.g. navigating back), React Query
 * serves the cached data instantly while revalidating in the background.
 */

import Sidebar from "@/components/layout/Sidebar";
import { StatCard } from "@/components/ui/Card";
import { useAuth } from "@/contexts/AuthContext";
import { recoveryApi } from "@/api/recovery";
import { workoutsApi } from "@/api/workouts";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const { data: workouts = [] } = useQuery({
    queryKey: ["workouts"],
    queryFn: () => workoutsApi.list(0, 5),
    enabled: !!user,
  });

  const { data: recovery = [] } = useQuery({
    queryKey: ["recovery"],
    queryFn: () => recoveryApi.list(0, 7),
    enabled: !!user,
  });

  const latest = recovery[0];

  if (loading) {
    return (
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 p-8 flex items-center justify-center">
          <p className="text-gray-400">Loading…</p>
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 max-w-5xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">Dashboard</h1>
        <p className="text-gray-500 text-sm mb-8">Welcome back, {user?.email}</p>

        <section className="mb-10">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-4">
            Latest recovery
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <StatCard label="Recovery score" value={latest?.whoop_recovery_score?.toFixed(0)} unit="%" color="text-green-600" />
            <StatCard label="HRV" value={latest?.hrv_ms?.toFixed(1)} unit="ms" />
            <StatCard label="Resting HR" value={latest?.resting_hr} unit="bpm" color="text-red-500" />
            <StatCard label="Sleep score" value={latest?.sleep_score?.toFixed(0)} unit="%" color="text-purple-600" />
          </div>
        </section>

        <section>
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-4">
            Recent workouts
          </h2>
          {workouts.length === 0 ? (
            <p className="text-gray-400 text-sm">No workouts logged yet.</p>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100 overflow-hidden">
              {workouts.map((w) => (
                <div key={w.id} className="flex items-center justify-between px-5 py-3.5">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{w.type ?? "Workout"}</p>
                    <p className="text-xs text-gray-400">{w.date ?? "—"}</p>
                  </div>
                  <div className="flex gap-6 text-right">
                    <div>
                      <p className="text-xs text-gray-400">TSS</p>
                      <p className="text-sm font-semibold text-brand-600">{w.tss?.toFixed(1) ?? "—"}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-400">Distance</p>
                      <p className="text-sm font-semibold text-gray-700">
                        {w.distance_meters ? `${(w.distance_meters / 1000).toFixed(1)} km` : "—"}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
