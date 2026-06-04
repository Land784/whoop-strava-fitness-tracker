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
