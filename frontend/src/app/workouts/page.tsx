"use client";

import Sidebar from "@/components/layout/Sidebar";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { useAuth } from "@/contexts/AuthContext";
import { workoutsApi } from "@/api/workouts";
import type { WorkoutCreate } from "@/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const emptyForm: WorkoutCreate = {};

export default function WorkoutsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<WorkoutCreate>(emptyForm);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  // useQuery caches the result under the key ["workouts"]. Any mutation
  // that invalidates this key will trigger an automatic background refetch.
  const { data: workouts = [], isLoading } = useQuery({
    queryKey: ["workouts"],
    queryFn: workoutsApi.list,
    enabled: !!user,
  });

  // useMutation wraps the create call. onSuccess invalidates the cache so
  // the list refetches automatically — no manual state updates needed.
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
    createMutation.mutate({
      ...form,
      duration_seconds: form.duration_seconds ? Number(form.duration_seconds) : undefined,
      distance_meters: form.distance_meters ? Number(form.distance_meters) : undefined,
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
            <h1 className="text-2xl font-bold text-gray-900">Workouts</h1>
            <p className="text-gray-500 text-sm mt-0.5">{workouts.length} total</p>
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

        {showForm && (
          <Card title="New workout" className="mb-8">
            <form onSubmit={handleCreate} className="grid grid-cols-2 gap-4">
              {createMutation.isError && (
                <div className="col-span-2 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-2">
                  {(createMutation.error as Error).message}
                </div>
              )}
              {[
                { label: "Type", key: "type", type: "text", placeholder: "Run" },
                { label: "Date", key: "date", type: "date" },
                { label: "Duration (s)", key: "duration_seconds", type: "number", placeholder: "3600" },
                { label: "Distance (m)", key: "distance_meters", type: "number", placeholder: "10000" },
                { label: "Avg HR", key: "avg_hr", type: "number", placeholder: "145" },
                { label: "TSS", key: "tss", type: "number", placeholder: "65.0", step: "0.1" },
              ].map(({ label, key, type, placeholder, step }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
                  <input
                    type={type}
                    step={step}
                    placeholder={placeholder}
                    value={(form[key as keyof WorkoutCreate] as string | undefined) ?? ""}
                    onChange={(e) => field(key as keyof WorkoutCreate, e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
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
          <p className="text-gray-400 text-sm">Loading…</p>
        ) : workouts.length === 0 ? (
          <p className="text-gray-400 text-sm">No workouts yet. Log your first one above.</p>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  {["Type", "Date", "TSS", "Distance", "Avg HR", ""].map((h) => (
                    <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {workouts.map((w) => (
                  <tr key={w.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-5 py-3 font-medium text-gray-900">{w.type ?? "—"}</td>
                    <td className="px-5 py-3 text-gray-500">{w.date ?? "—"}</td>
                    <td className="px-5 py-3 text-brand-600 font-semibold">{w.tss?.toFixed(1) ?? "—"}</td>
                    <td className="px-5 py-3 text-gray-700">
                      {w.distance_meters ? `${(w.distance_meters / 1000).toFixed(1)} km` : "—"}
                    </td>
                    <td className="px-5 py-3 text-gray-700">{w.avg_hr ?? "—"}</td>
                    <td className="px-5 py-3 text-right">
                      <button
                        onClick={() => deleteMutation.mutate(w.id)}
                        className="text-red-400 hover:text-red-600 text-xs transition-colors"
                      >
                        Delete
                      </button>
                    </td>
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
