"use client";

import Sidebar from "@/components/layout/Sidebar";
import Button from "@/components/ui/Button";
import Card, { StatCard } from "@/components/ui/Card";
import { useAuth } from "@/contexts/AuthContext";
import { workoutsApi } from "@/api/workouts";
import { formatDuration, formatMiles, formatPace, metersToMiles } from "@/lib/format";
import type { WorkoutCreate } from "@/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

const emptyForm: WorkoutCreate = {};
const METERS_PER_MILE = 1609.344;
const PAGE_SIZE = 15;
const HISTORY_LIMIT = 200; // how much history we load to summarise past weeks

/** Local midnight of the most recent Monday — the start of "this week". */
function thisMonday(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  const mondayOffset = (d.getDay() + 6) % 7; // Sun=0 -> 6, Mon=1 -> 0, ...
  d.setDate(d.getDate() - mondayOffset);
  return d;
}

/** [start, end) for the week `offset` weeks before this one (end is exclusive). */
function weekRange(offset: number): { start: Date; end: Date } {
  const start = thisMonday();
  start.setDate(start.getDate() + offset * 7);
  const end = new Date(start);
  end.setDate(start.getDate() + 7);
  return { start, end };
}

const fmtDay = (d: Date) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });

export default function WorkoutsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<WorkoutCreate>(emptyForm);
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [weekOffset, setWeekOffset] = useState(0); // 0 = this week, -1 = last week

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  // One history query feeds both the paginated table (sliced client-side) and
  // the weekly summary (filtered by the selected week).
  const { data: history = [], isLoading } = useQuery({
    queryKey: ["workouts", "history"],
    queryFn: () => workoutsApi.list(0, HISTORY_LIMIT),
    enabled: !!user,
  });

  // Summary for the selected week only.
  const weekly = useMemo(() => {
    const { start, end } = weekRange(weekOffset);
    const inWeek = history.filter((w) => {
      if (!w.date) return false;
      const d = new Date(`${w.date}T00:00:00`); // parse as local, not UTC
      return d >= start && d < end;
    });
    const totalMeters = inWeek.reduce((s, w) => s + (w.distance_meters ?? 0), 0);
    const totalSeconds = inWeek.reduce((s, w) => s + (w.duration_seconds ?? 0), 0);
    const withHr = inWeek.filter((w) => w.avg_hr != null);
    const avgHr = withHr.length
      ? Math.round(withHr.reduce((s, w) => s + (w.avg_hr ?? 0), 0) / withHr.length)
      : null;
    return { count: inWeek.length, totalMeters, totalSeconds, avgHr };
  }, [history, weekOffset]);

  const { start, end } = weekRange(weekOffset);
  const lastDay = new Date(end);
  lastDay.setDate(end.getDate() - 1);
  const rangeLabel = `${fmtDay(start)} – ${fmtDay(lastDay)}`;
  const relativeLabel = weekOffset === 0 ? "This week" : weekOffset === -1 ? "Last week" : null;

  const rows = history.slice(0, visible);
  const hasMore = visible < history.length;

  const createMutation = useMutation({
    mutationFn: workoutsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workouts"] });
      setShowForm(false);
      setForm(emptyForm);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: workoutsApi.remove,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workouts"] }),
  });

  const syncMutation = useMutation({
    mutationFn: workoutsApi.sync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workouts"] }),
  });

  function field(key: keyof WorkoutCreate, value: string) {
    setForm((f) => ({ ...f, [key]: value === "" ? undefined : value }));
  }

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    // The form collects imperial/friendly units; convert to the API's SI units.
    createMutation.mutate({
      ...form,
      duration_seconds: form.duration_seconds ? Math.round(Number(form.duration_seconds) * 60) : undefined,
      distance_meters: form.distance_meters ? Number(form.distance_meters) * METERS_PER_MILE : undefined,
      avg_hr: form.avg_hr ? Number(form.avg_hr) : undefined,
      tss: form.tss ? Number(form.tss) : undefined,
    });
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 max-w-5xl">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-display text-2xl font-bold text-white">Workouts</h1>
            <p className="text-slate-500 text-sm mt-0.5">Your training log</p>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => syncMutation.mutate()} loading={syncMutation.isPending}>
              Sync
            </Button>
            <Button onClick={() => setShowForm((s) => !s)}>
              {showForm ? "Cancel" : "+ Log workout"}
            </Button>
          </div>
        </div>

        {/* Week navigator + summary */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-xs font-semibold text-slate-500 uppercase tracking-widest">
              {relativeLabel ?? "Week"} summary
            </h2>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setWeekOffset((o) => o - 1)}
                aria-label="Previous week"
                className="h-8 w-8 grid place-items-center rounded-lg border border-line text-slate-400 hover:bg-white/5 hover:text-slate-100 transition-colors cursor-pointer"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
              </button>
              <span className="text-sm text-slate-200 min-w-[120px] text-center tabular-nums">{rangeLabel}</span>
              <button
                onClick={() => setWeekOffset((o) => Math.min(0, o + 1))}
                disabled={weekOffset >= 0}
                aria-label="Next week"
                className="h-8 w-8 grid place-items-center rounded-lg border border-line text-slate-400 hover:bg-white/5 hover:text-slate-100 transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 18l6-6-6-6" /></svg>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <StatCard label="Workouts" value={weekly.count} />
            <StatCard label="Distance" value={metersToMiles(weekly.totalMeters).toFixed(1)} unit="mi" color="text-sky-400" />
            <StatCard label="Time" value={weekly.totalSeconds ? formatDuration(weekly.totalSeconds) : "—"} color="text-slate-100" />
            <StatCard label="Avg HR" value={weekly.avgHr ?? "—"} unit={weekly.avgHr ? "bpm" : undefined} color="text-rose-400" />
          </div>
        </div>

        {showForm && (
          <Card title="New workout" className="mb-8">
            <form onSubmit={handleCreate} className="grid grid-cols-2 gap-4">
              {createMutation.isError && (
                <div className="col-span-2 bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm rounded-lg px-4 py-2">
                  {(createMutation.error as Error).message}
                </div>
              )}
              {[
                { label: "Type", key: "type", type: "text", placeholder: "Run" },
                { label: "Date", key: "date", type: "date" },
                { label: "Duration (min)", key: "duration_seconds", type: "number", placeholder: "45" },
                { label: "Distance (mi)", key: "distance_meters", type: "number", placeholder: "6.2", step: "0.01" },
                { label: "Avg HR", key: "avg_hr", type: "number", placeholder: "145" },
                { label: "TSS", key: "tss", type: "number", placeholder: "65.0", step: "0.1" },
              ].map(({ label, key, type, placeholder, step }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-slate-400 mb-1">{label}</label>
                  <input
                    type={type}
                    step={step}
                    placeholder={placeholder}
                    value={(form[key as keyof WorkoutCreate] as string | undefined) ?? ""}
                    onChange={(e) => field(key as keyof WorkoutCreate, e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-line text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-400/60 focus:border-transparent transition-colors"
                  />
                </div>
              ))}
              <div className="col-span-2 flex justify-end">
                <Button type="submit" loading={createMutation.isPending}>Save workout</Button>
              </div>
            </form>
          </Card>
        )}

        {isLoading ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : history.length === 0 ? (
          <p className="text-slate-500 text-sm">No workouts yet. Log one above, or connect Strava in Settings and Sync.</p>
        ) : (
          <>
            <div className="bg-panel rounded-2xl border border-line overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-white/5 border-b border-line">
                  <tr>
                    {["Activity", "Date", "Duration", "Distance", "Pace", "Avg HR", ""].map((h) => (
                      <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {rows.map((w) => (
                    <tr key={w.id} className="hover:bg-white/5 transition-colors">
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <div className="h-8 w-8 rounded-lg bg-sky-400/10 grid place-items-center shrink-0">
                            <svg className="w-4 h-4 text-sky-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                              <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />
                            </svg>
                          </div>
                          <div>
                            <p className="font-medium text-slate-100">{w.type ?? "Workout"}</p>
                            {w.source === "strava" ? (
                              <span className="inline-flex items-center gap-1 text-[10px] text-[#FC4C02] font-medium">
                                <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="#FC4C02"><path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169" /></svg>
                                Strava
                              </span>
                            ) : w.source === "whoop" ? (
                              <span className="inline-flex items-center gap-1 text-[10px] text-sky-400 font-medium">
                                <span className="w-2 h-2 rounded-full border border-sky-400 inline-block" />
                                WHOOP
                              </span>
                            ) : (
                              <span className="text-[10px] text-slate-500">Manual</span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3 text-slate-500">{w.date ?? "—"}</td>
                      <td className="px-5 py-3 text-slate-300">{formatDuration(w.duration_seconds)}</td>
                      <td className="px-5 py-3 text-slate-100 font-medium">{formatMiles(w.distance_meters)}</td>
                      <td className="px-5 py-3 text-emerald-400">{formatPace(w.distance_meters, w.duration_seconds)}</td>
                      <td className="px-5 py-3 text-slate-300">{w.avg_hr ?? "—"}</td>
                      <td className="px-5 py-3 text-right">
                        <button
                          onClick={() => deleteMutation.mutate(w.id)}
                          className="text-rose-400 hover:text-rose-300 text-xs transition-colors cursor-pointer"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {hasMore && (
              <div className="flex justify-center mt-5">
                <Button variant="secondary" onClick={() => setVisible((v) => v + PAGE_SIZE)}>
                  Show more
                </Button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
