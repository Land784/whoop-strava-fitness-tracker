import { request, streamRequest } from "@/lib/http";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface DailyBriefing {
  date: string;
  generated_at: string;
  recovery: string;
  state: string;
  recommended_workout: string;
}

export const aiApi = {
  // Today's dashboard briefing. The backend generates it once per day and
  // caches it, so repeated calls are cheap reads, not new Claude requests.
  dailyBriefing: () => request<DailyBriefing>("/ai/daily-briefing"),

  insights: (question: string) =>
    request<{ insight: string }>("/ai/insights", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),

  // Streaming, multi-turn chat. Send the whole history each turn (that's how
  // the model "remembers"); onText fires for every token chunk as it streams.
  streamChat: (messages: ChatMessage[], onText: (text: string) => void) =>
    streamRequest("/ai/chat", { messages }, onText),

  generatePlan: (weekStart: string) =>
    request<{ id: number; plan_json: string; week_start: string }>("/ai/training-plan", {
      method: "POST",
      body: JSON.stringify({ week_start: weekStart }),
    }),
};
