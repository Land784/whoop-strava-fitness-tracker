/**
 * Base HTTP helper used by every api/ module.
 * Lives here so all network concerns (base URL, auth header, error shape)
 * are in one place. api/ files import this and never call fetch directly.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

export async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

/**
 * POST a JSON body and consume a Server-Sent Events stream from the response,
 * invoking `onText` for each text chunk as it arrives.
 *
 * We can't use the browser's built-in EventSource here: it's GET-only and
 * can't attach an Authorization header. So we drive the stream by hand —
 * fetch() + a ReadableStream reader + a tiny SSE parser.
 */
export async function streamRequest(
  path: string,
  body: unknown,
  onText: (text: string) => void,
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });

  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  // Network chunks don't line up with SSE frames, so we buffer and split on the
  // blank line ("\n\n") that delimits one event from the next.
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? ""; // last piece may be a partial frame — keep it

    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      const data = line.slice(5).trim();
      if (data === "[DONE]") return;

      const parsed = JSON.parse(data) as { text?: string; error?: string };
      if (parsed.error) throw new Error(parsed.error);
      if (parsed.text) onText(parsed.text);
    }
  }
}
