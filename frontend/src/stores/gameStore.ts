/**
 * Game store using Zustand.
 */

import { create } from "zustand";

interface Player {
  seat: number;
  role?: string;
  is_alive: boolean;
  agent_id?: string;
}

interface GameEvent {
  event: string;
  data: Record<string, any>;
  timestamp: string;
}

interface GameStore {
  roomId: string | null;
  phase: string;
  round: number;
  players: Player[];
  events: GameEvent[];
  winner: string | null;
  connected: boolean;

  setRoomId: (id: string) => void;
  setPhase: (phase: string) => void;
  setRound: (round: number) => void;
  setPlayers: (players: Player[]) => void;
  addEvent: (event: GameEvent) => void;
  setWinner: (winner: string) => void;
  setConnected: (connected: boolean) => void;
  updatePlayer: (seat: number, updates: Partial<Player>) => void;
  reset: () => void;
}

export const useGameStore = create<GameStore>((set) => ({
  roomId: null,
  phase: "waiting",
  round: 0,
  players: [],
  events: [],
  winner: null,
  connected: false,

  setRoomId: (id) => set({ roomId: id }),
  setPhase: (phase) => set({ phase }),
  setRound: (round) => set({ round }),
  setPlayers: (players) => set({ players }),
  addEvent: (event) => set((state) => ({ events: [...state.events, event] })),
  setWinner: (winner) => set({ winner }),
  setConnected: (connected) => set({ connected }),
  updatePlayer: (seat, updates) =>
    set((state) => ({
      players: state.players.map((p) =>
        p.seat === seat ? { ...p, ...updates } : p
      ),
    })),
  reset: () =>
    set({
      roomId: null,
      phase: "waiting",
      round: 0,
      players: [],
      events: [],
      winner: null,
      connected: false,
    }),
}));
