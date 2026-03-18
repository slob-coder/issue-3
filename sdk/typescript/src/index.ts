/**
 * Werewolf Arena TypeScript SDK
 */

export interface RoomConfig {
  player_count: number;
  roles: Record<string, number>;
  speech_timeout?: number;
  action_timeout?: number;
  vote_timeout?: number;
}

export interface Room {
  id: string;
  name: string;
  status: string;
  config: RoomConfig;
  created_at: string;
  player_count: number;
}

export interface Agent {
  id: string;
  name: string;
  api_key: string;
}

export interface GameEvent {
  event: string;
  room_id: string;
  data: Record<string, any>;
  timestamp: string;
}

export class WerewolfClient {
  private baseUrl: string;
  private apiKey?: string;

  constructor(baseUrl: string = "http://localhost:8000", apiKey?: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.apiKey) h["X-API-Key"] = this.apiKey;
    return h;
  }

  async registerAgent(name: string, owner?: string): Promise<Agent> {
    const resp = await fetch(`${this.baseUrl}/api/v1/agents`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ name, owner }),
    });
    const data = await resp.json();
    this.apiKey = data.api_key;
    return data;
  }

  async createRoom(name: string, config: RoomConfig): Promise<Room> {
    const resp = await fetch(`${this.baseUrl}/api/v1/rooms`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ name, config }),
    });
    return resp.json();
  }

  async joinRoom(roomId: string): Promise<{ seat: number; player_id: string }> {
    const resp = await fetch(`${this.baseUrl}/api/v1/rooms/${roomId}/join`, {
      method: "POST",
      headers: this.headers(),
    });
    return resp.json();
  }

  async listRooms(status?: string): Promise<{ rooms: Room[]; total: number }> {
    const params = status ? `?status=${status}` : "";
    const resp = await fetch(`${this.baseUrl}/api/v1/rooms${params}`, {
      headers: this.headers(),
    });
    return resp.json();
  }

  async getRoomState(roomId: string): Promise<Record<string, any>> {
    const resp = await fetch(`${this.baseUrl}/api/v1/rooms/${roomId}/state`, {
      headers: this.headers(),
    });
    return resp.json();
  }

  async submitAction(
    roomId: string,
    action: string,
    data: Record<string, any>
  ): Promise<void> {
    await fetch(`${this.baseUrl}/api/v1/rooms/${roomId}/actions`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ action, data }),
    });
  }

  async getReplay(roomId: string): Promise<Record<string, any>> {
    const resp = await fetch(`${this.baseUrl}/api/v1/rooms/${roomId}/replay`, {
      headers: this.headers(),
    });
    return resp.json();
  }

  connectWs(
    roomId: string,
    onMessage: (event: GameEvent) => void
  ): WebSocket {
    const wsUrl = this.baseUrl.replace("http", "ws");
    const ws = new WebSocket(
      `${wsUrl}/ws/agent/${roomId}?api_key=${this.apiKey}`
    );
    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      onMessage(data);
    };
    return ws;
  }
}
