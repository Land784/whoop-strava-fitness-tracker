"use client";

import Sidebar from "@/components/layout/Sidebar";
import Button from "@/components/ui/Button";
import { useAuth } from "@/contexts/AuthContext";
import { aiApi } from "@/api/ai";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const SUGGESTIONS = [
  "Give me a summary of my recent fitness trends",
  "Am I ready for a hard workout today?",
  "How has my HRV been trending?",
  "What can I improve about my recovery?",
];

export default function AIPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // useMutation is ideal for the chat pattern: each send is a one-off
  // request with its own loading state, not a cached query.
  const insightMutation = useMutation({
    mutationFn: (question: string) => aiApi.insights(question),
    onSuccess: (data) => {
      setMessages((m) => [...m, { role: "assistant", content: data.insight }]);
    },
    onError: (err) => {
      setMessages((m) => [...m, {
        role: "assistant",
        content: `Error: ${err instanceof Error ? err.message : "Request failed"}`,
      }]);
    },
  });

  function send(question: string) {
    if (!question.trim() || insightMutation.isPending) return;
    setMessages((m) => [...m, { role: "user", content: question }]);
    setInput("");
    insightMutation.mutate(question);
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 flex flex-col p-8 max-w-3xl">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">AI Insights</h1>
          <p className="text-gray-500 text-sm mt-0.5">Ask your personal AI fitness coach anything.</p>
        </div>

        <div className="flex-1 bg-white rounded-xl border border-gray-200 flex flex-col overflow-hidden mb-4">
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {messages.length === 0 && !insightMutation.isPending && (
              <div className="h-full flex flex-col items-center justify-center text-center py-10">
                <div className="w-12 h-12 bg-brand-50 rounded-full flex items-center justify-center mb-4">
                  <svg className="w-6 h-6 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                  </svg>
                </div>
                <p className="text-gray-500 text-sm mb-6">Start a conversation about your fitness data</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-md">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="text-left text-xs text-gray-600 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-lg px-3 py-2.5 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                  msg.role === "user"
                    ? "bg-brand-600 text-white rounded-br-sm"
                    : "bg-gray-100 text-gray-800 rounded-bl-sm"
                }`}>
                  {msg.content}
                </div>
              </div>
            ))}

            {insightMutation.isPending && (
              <div className="flex justify-start">
                <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-3">
                  <div className="flex gap-1 items-center h-4">
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-gray-100 p-4">
            <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about your fitness data…"
                className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
              <Button type="submit" loading={insightMutation.isPending} disabled={!input.trim()}>
                Send
              </Button>
            </form>
          </div>
        </div>
      </main>
    </div>
  );
}
