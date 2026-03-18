"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";

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

const ROLE_COLORS: Record<string, string> = {
  werewolf: "text-red-400",
  seer: "text-purple-400",
  witch: "text-green-400",
  hunter: "text-yellow-400",
  villager: "text-blue-400",
};

const ROLE_NAMES: Record<string, string> = {
  werewolf: "🐺 狼人",
  seer: "🔮 预言家",
  witch: "🧪 女巫",
  hunter: "🎯 猎人",
  villager: "👤 村民",
};

export default function RoomPage() {
  const { roomId } = useParams<{ roomId: string }>();
  const [players, setPlayers] = useState<Player[]>([]);
  const [events, setEvents] = useState<GameEvent[]>([]);
  const [phase, setPhase] = useState("waiting");
  const [round, setRound] = useState(0);
  const [winner, setWinner] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const eventsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Fetch initial state
    fetch(`/api/v1/rooms/${roomId}/state`)
      .then((r) => r.json())
      .then((data) => {
        setPlayers(data.players || []);
        setPhase(data.phase || data.status);
        setRound(data.round || 0);
      });

    // Connect WebSocket
    const wsUrl = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/spectate/${roomId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (evt) => {
      const msg: GameEvent = JSON.parse(evt.data);
      setEvents((prev) => [...prev, msg]);
      handleEvent(msg);
    };

    return () => ws.close();
  }, [roomId]);

  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  function handleEvent(msg: GameEvent) {
    const { event, data } = msg;

    if (event === "game.start") {
      setPlayers(
        data.players?.map((p: any) => ({
          seat: p.seat,
          role: p.role,
          is_alive: true,
        })) || []
      );
      setPhase("night");
    } else if (event === "phase.night") {
      setPhase("night");
      setRound(data.round || round);
    } else if (event === "phase.result" || event === "phase.execution") {
      if (data.eliminated_seat) {
        setPlayers((prev) =>
          prev.map((p) =>
            p.seat === data.eliminated_seat ? { ...p, is_alive: false } : p
          )
        );
      }
      if (data.eliminated) {
        setPlayers((prev) =>
          prev.map((p) => {
            const elim = data.eliminated.find((e: any) => e.seat === p.seat);
            return elim ? { ...p, is_alive: false } : p;
          })
        );
      }
    } else if (event === "phase.day" || event === "phase.day.vote") {
      setPhase(event === "phase.day.vote" ? "vote" : "day");
    } else if (event === "game.end") {
      setWinner(data.winner);
      setPhase("finished");
    }
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">🐺 Room Spectator</h1>
          <p className="text-sm text-slate-400">
            Round {round} ·{" "}
            <span
              className={
                phase === "night"
                  ? "text-indigo-400"
                  : phase === "day"
                  ? "text-yellow-400"
                  : "text-slate-400"
              }
            >
              {phase === "night"
                ? "🌙 夜晚"
                : phase === "day"
                ? "☀️ 白天"
                : phase === "vote"
                ? "🗳️ 投票"
                : phase === "finished"
                ? "🏁 结束"
                : "⏳ 等待"}
            </span>
          </p>
        </div>
        <div
          className={`px-3 py-1 rounded-full text-xs ${
            connected ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
          }`}
        >
          {connected ? "● 已连接" : "○ 未连接"}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Player Seats */}
        <div className="lg:col-span-1">
          <div className="glass-card p-4">
            <h2 className="font-medium mb-4">座位</h2>
            <div className="grid grid-cols-2 gap-3">
              {players.map((p) => (
                <div
                  key={p.seat}
                  className={`p-3 rounded-lg border text-center transition-all ${
                    p.is_alive
                      ? "border-green-500/30 bg-green-500/5"
                      : "border-red-500/30 bg-red-500/5 opacity-50"
                  }`}
                >
                  <div className="text-2xl mb-1">
                    {p.is_alive ? "👤" : "💀"}
                  </div>
                  <div className="font-medium">#{p.seat}</div>
                  {p.role && (
                    <div className={`text-xs mt-1 ${ROLE_COLORS[p.role] || "text-slate-400"}`}>
                      {ROLE_NAMES[p.role] || p.role}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {winner && (
            <div className="glass-card p-4 mt-4 text-center">
              <div className="text-3xl mb-2">
                {winner === "werewolf" ? "🐺" : "👥"}
              </div>
              <div className="font-bold text-lg">
                {winner === "werewolf" ? "狼人胜利" : "好人胜利"}
              </div>
            </div>
          )}
        </div>

        {/* Event Log */}
        <div className="lg:col-span-2">
          <div className="glass-card p-4 h-[600px] flex flex-col">
            <h2 className="font-medium mb-4">📋 事件日志</h2>
            <div className="flex-1 overflow-y-auto space-y-2">
              {events.length === 0 ? (
                <div className="text-center text-slate-400 py-8">
                  等待游戏开始...
                </div>
              ) : (
                events.map((ev, i) => (
                  <EventCard key={i} event={ev} />
                ))
              )}
              <div ref={eventsEndRef} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function EventCard({ event }: { event: GameEvent }) {
  const { event: type, data } = event;
  let icon = "📌";
  let text = type;

  if (type === "game.start") {
    icon = "🎮";
    text = `游戏开始！${data.player_count} 名玩家`;
  } else if (type === "phase.night") {
    icon = "🌙";
    text = data.message || `第 ${data.round} 轮夜晚`;
  } else if (type === "phase.night.action") {
    icon = "🔪";
    text = `${data.role} (${data.seat}号) ${data.action}`;
    if (data.target_seat) text += ` → ${data.target_seat}号`;
  } else if (type === "phase.result") {
    icon = "⚰️";
    text = data.message || "夜晚结算";
  } else if (type === "day.speech.broadcast") {
    icon = "🗣️";
    text = `${data.seat}号: ${data.content}`;
  } else if (type === "day.speech.cot") {
    icon = "🧠";
    text = `${data.seat}号 [思考]: ${data.chain_of_thought}`;
  } else if (type === "phase.day.vote") {
    icon = "🗳️";
    text = data.message || "投票开始";
  } else if (type === "day.vote.cast") {
    icon = "✋";
    text = `${data.from_seat}号 → ${data.to_seat === 0 ? "弃权" : data.to_seat + "号"}`;
  } else if (type === "phase.execution") {
    icon = "⚔️";
    text = data.eliminated_seat
      ? `${data.eliminated_seat}号 (${data.eliminated_role || "?"}) 被投票淘汰`
      : data.is_tie
      ? "平票，无人淘汰"
      : "无人被淘汰";
  } else if (type === "game.end") {
    icon = data.winner === "werewolf" ? "🐺" : "👥";
    text = `游戏结束！${data.winner === "werewolf" ? "狼人" : "好人"}阵营获胜`;
  }

  return (
    <div className="px-3 py-2 bg-slate-800/30 rounded-lg text-sm">
      <span className="mr-2">{icon}</span>
      <span className="text-slate-300">{text}</span>
    </div>
  );
}
