"use client";

import Sidebar from "@/components/layout/Sidebar";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { useAuth } from "@/contexts/AuthContext";
import { recoveryApi } from "@/api/recovery";
import type { RecoveryCreate } from "@/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const today = new Date().toISOString().split("T")[0];
const emptyForm: RecoveryCreate = { date: today };

function scoreColor(score: number | null): string {
  if (score == null) return "text-slate-500";
  if (score >= 67) return "text-emerald-400";
  if (score >= 34) return "text-amber-400";
  return "text-rose-400";
}

export default function RecoveryPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<RecoveryCreate>(emptyForm);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  // Arrow wrapper keeps `records` typed as RecoveryScore[] (see workouts page).
  const { data: records = [], isLoading } = useQuery({
    queryKey: ["recovery"],
    queryFn: () => recoveryApi.list(),
    enabled: !!user,
  });

  const createMutation = useMutation({
    mutationFn: recoveryApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recovery"] });
      setShowForm(false);
      setForm(emptyForm);
    },
  });

  function field(key: keyof RecoveryCreate, value: string) {
    setForm((f) => ({ ...f, [key]: value === "" ? undefined : value }));
  }

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    createMutation.mutate({
      ...form,
      whoop_recovery_score: form.whoop_recovery_score ? Number(form.whoop_recovery_score) : undefined,
      hrv_ms: form.hrv_ms ? Number(form.hrv_ms) : undefined,
      resting_hr: form.resting_hr ? Number(form.resting_hr) : undefined,
      sleep_score: form.sleep_score ? Number(form.sleep_score) : undefined,
    });
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 max-w-5xl">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-display text-2xl font-bold text-white">Recovery</h1>
            <p className="text-slate-500 text-sm mt-0.5">{records.length} days logged</p>
          </div>
          <Button onClick={() => setShowForm((s) => !s)}>
            {showForm ? "Cancel" : "+ Log today"}
          </Button>
        </div>

        {showForm && (
          <Card title="New recovery entry" className="mb-8">
            <form onSubmit={handleCreate} className="grid grid-cols-2 gap-4">
              {createMutation.isError && (
                <div className="col-span-2 bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm rounded-lg px-4 py-2">
                  {(createMutation.error as Error).message}
                </div>
              )}
              {[
                { label: "Date", key: "date", type: "date" },
                { label: "Recovery score (0–100)", key: "whoop_recovery_score", type: "number", placeholder: "75" },
                { label: "HRV (ms)", key: "hrv_ms", type: "number", placeholder: "65.4", step: "0.1" },
                { label: "Resting HR (bpm)", key: "resting_hr", type: "number", placeholder: "52" },
                { label: "Sleep score (%)", key: "sleep_score", type: "number", placeholder: "85" },
              ].map(({ label, key, type, placeholder, step }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-slate-400 mb-1">{label}</label>
                  <input
                    type={type}
                    step={step}
                    placeholder={placeholder}
                    value={(form[key as keyof RecoveryCreate] as string | undefined) ?? ""}
                    onChange={(e) => field(key as keyof RecoveryCreate, e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-white/5 border border-line text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-400/60 focus:border-transparent transition-colors"
                  />
                </div>
              ))}
              <div className="col-span-2 flex justify-end">
                <Button type="submit" loading={createMutation.isPending}>Save entry</Button>
              </div>
            </form>
          </Card>
        )}

        {isLoading ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : records.length === 0 ? (
          <p className="text-slate-500 text-sm">No recovery data yet. Connect WHOOP and Sync, or log a day manually.</p>
        ) : (
          <div className="bg-panel rounded-2xl border border-line overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-white/5 border-b border-line">
                <tr>
                  {["Date", "Score", "HRV", "Resting HR", "Sleep"].map((h) => (
                    <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {records.map((r) => (
                  <tr key={r.id} className="hover:bg-white/5 transition-colors">
                    <td className="px-5 py-3 font-medium text-slate-100">{r.date}</td>
                    <td className={`px-5 py-3 font-bold ${scoreColor(r.whoop_recovery_score)}`}>
                      {r.whoop_recovery_score?.toFixed(0) ?? "—"}
                    </td>
                    <td className="px-5 py-3 text-slate-300">{r.hrv_ms?.toFixed(1) ?? "—"} <span className="text-slate-500 text-xs">ms</span></td>
                    <td className="px-5 py-3 text-slate-300">{r.resting_hr ?? "—"} <span className="text-slate-500 text-xs">bpm</span></td>
                    <td className="px-5 py-3 text-slate-300">{r.sleep_score?.toFixed(0) ?? "—"}<span className="text-slate-500 text-xs">%</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
