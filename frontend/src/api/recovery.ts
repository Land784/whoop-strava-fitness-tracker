import { request } from "@/lib/http";
import type { RecoveryScore, RecoveryCreate } from "@/types";

export const recoveryApi = {
  list: (skip = 0, limit = 30) =>
    request<RecoveryScore[]>(`/recovery/?skip=${skip}&limit=${limit}`),

  get: (id: number) =>
    request<RecoveryScore>(`/recovery/${id}`),

  create: (data: RecoveryCreate) =>
    request<RecoveryScore>("/recovery/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
