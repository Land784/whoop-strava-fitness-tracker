"use client";

/**
 * Wraps the app with all React context providers.
 *
 * Why a separate Providers component? Next.js App Router layout files must be
 * server components by default, but context providers require "use client".
 * Splitting providers into their own client component lets layout.tsx stay a
 * server component (better for performance) while still giving the whole tree
 * access to these contexts.
 */

import { AuthProvider } from "@/contexts/AuthContext";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  // useState ensures each browser session gets its own QueryClient instance.
  // Creating it outside the component would share it across server renders,
  // leaking one user's cached data into another user's session.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Don't retry failed requests automatically — a 401 on every page
            // would fire 3 retries before redirecting to login otherwise
            retry: false,
            staleTime: 30_000, // data is "fresh" for 30s before a background refetch
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}
