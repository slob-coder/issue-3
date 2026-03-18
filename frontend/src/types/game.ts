/**
 * Type definitions for the frontend.
 */

export interface Room {
  id: string;
  name: string;
  status: "waiting" | "playing" | "finished";
  config: RoomConfig;
  created_at: string;
  player_count: number;
  winner?: string;
}

export interface RoomConfig {
  player_count: number;
  roles: Record<string, number>;
  speech_timeout: number;
  action_timeout: number;
  vote_timeout: number;
}

export interface Player {
  seat: number;
  role?: string;
  is_alive: boolean;
  agent_id?: string;
  agent_name?: string;
  eliminated_at_round?: number;
  elimination_reason?: string;
}

export interface GameEvent {
  event: string;
  room_id: string;
  data: Record<string, any>;
  timestamp: string;
}

export type GamePhase =
  | "waiting"
  | "night"
  | "result"
  | "day_speech"
  | "day_vote"
  | "execution"
  | "check_win"
  | "finished";

export type Role = "werewolf" | "seer" | "witch" | "hunter" | "villager";
export type Faction = "werewolf" | "villager";
