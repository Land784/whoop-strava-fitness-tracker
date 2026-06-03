import { request } from "@/lib/http";
import type { Workout, WorkoutCreate } from "@/types";

export const workoutsApi = {
  list: (skip = 0, limit = 50) =>
    request<Workout[]>(`/workouts/?skip=${skip}&limit=${limit}`),

  get: (id: number) =>
    request<Workout>(`/workouts/${id}`),

  create: (data: WorkoutCreate) =>
    request<Workout>("/workouts/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  remove: (id: number) =>
    request<void>(`/workouts/${id}`, { method: "DELETE" }),

  sync: () =>
    request<Record<string, number | string>>("/workouts/sync", { method: "POST" }),
};
