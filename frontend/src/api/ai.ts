import { request, streamRequest } from "@/lib/http";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export const aiApi = {
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
