import { request } from "@/lib/http";
import type { ConnectionStatus, Token, User } from "@/types";

export const authApi = {
  register: (email: string, password: string) =>
    request<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<Token>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  // The current user, resolved from the stored JWT. The app calls this on boot
  // to confirm the token is still valid (a 401 means it expired) and to get the
  // real user record — never a locally-faked one.
  me: () => request<User>("/auth/me"),

  // Which providers the current user has connected (booleans, no tokens).
  getConnections: () => request<ConnectionStatus>("/auth/connections"),

  // Returns a provider authorize URL (with our signed `state`). The caller does
  // a full-page redirect to it — see the Settings page.
  getStravaAuthorizeUrl: () =>
    request<{ authorization_url: string }>("/auth/strava/authorize"),

  getWhoopAuthorizeUrl: () =>
    request<{ authorization_url: string }>("/auth/whoop/authorize"),

  getDexcomAuthorizeUrl: () =>
    request<{ authorization_url: string }>("/auth/dexcom/authorize"),
};
