export interface User {
  id: number;
  email: string;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export interface ConnectionStatus {
  strava_connected: boolean;
  whoop_connected: boolean;
  dexcom_connected: boolean;
}

export interface Workout {
  id: number;
  user_id: number;
  strava_id: string | null;
  whoop_id: string | null;
  source: string; // "strava" | "whoop" | "manual"
  type: string | null;
  date: string | null;
  duration_seconds: number | null;
  distance_meters: number | null;
  avg_hr: number | null;
  tss: number | null;
  created_at: string;
}

export interface WorkoutCreate {
  type?: string;
  date?: string;
  duration_seconds?: number;
  distance_meters?: number;
  avg_hr?: number;
  tss?: number;
}

export interface RecoveryScore {
  id: number;
  user_id: number;
  date: string;
  whoop_recovery_score: number | null;
  hrv_ms: number | null;
  resting_hr: number | null;
  sleep_score: number | null;
  created_at: string;
}

export interface RecoveryCreate {
  date: string;
  whoop_recovery_score?: number;
  hrv_ms?: number;
  resting_hr?: number;
  sleep_score?: number;
}

export interface TrainingPlan {
  id: number;
  user_id: number;
  generated_at: string;
  week_start: string;
  plan_json: string;
  prompt_summary: string | null;
}
