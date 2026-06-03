import { request } from "@/lib/http";

export const aiApi = {
  insights: (question: string) =>
    request<{ insight: string }>("/ai/insights", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),

  generatePlan: (weekStart: string) =>
    request<{ id: number; plan_json: string; week_start: string }>("/ai/training-plan", {
      method: "POST",
      body: JSON.stringify({ week_start: weekStart }),
    }),
};
