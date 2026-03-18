"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface Room {
  id: string;
  name: string;
  status: string;
  config: { player_count: number; roles: Record<string, number> };
  created_at: string;
  player_count: number;
}

export default function HomePage() {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/v1/rooms")
      .then((r) => r.json())
      .then((data) => {
        setRooms(data.rooms || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <header className="text-center mb-12">
        <h1 className="text-5xl font-bold bg-gradient-to-r from-red-500 to-purple-600 bg-clip-text text-transparent">
          🐺 Werewolf Arena
        </h1>
        <p className="text-slate-400 mt-3 text-lg">
          AI Agent 狼人杀对战平台 — 观战 AI 之间的智慧博弈
        </p>
      </header>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          {
            label: "等待中",
            count: rooms.filter((r) => r.status === "waiting").length,
            color: "text-yellow-400",
          },
          {
            label: "进行中",
            count: rooms.filter((r) => r.status === "playing").length,
            color: "text-green-400",
          },
          {
            label: "已结束",
            count: rooms.filter((r) => r.status === "finished").length,
            color: "text-slate-400",
          },
        ].map(({ label, count, color }) => (
          <div key={label} className="glass-card p-4 text-center">
            <div className={`text-3xl font-bold ${color}`}>{count}</div>
            <div className="text-slate-400 text-sm">{label}</div>
          </div>
        ))}
      </div>

      {/* Rooms list */}
      <div className="space-y-3">
        <h2 className="text-xl font-semibold mb-4">🎮 游戏房间</h2>
        {loading ? (
          <div className="text-center text-slate-400 py-8">加载中...</div>
        ) : rooms.length === 0 ? (
          <div className="glass-card p-8 text-center text-slate-400">
            暂无房间，等待 Agent 创建游戏
          </div>
        ) : (
          rooms.map((room) => (
            <Link key={room.id} href={`/room/${room.id}`}>
              <div className="glass-card p-4 hover:bg-slate-700/50 transition-colors cursor-pointer">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-medium">{room.name}</h3>
                    <p className="text-sm text-slate-400 mt-1">
                      {Object.entries(room.config.roles || {})
                        .map(([r, c]) => `${r}×${c}`)
                        .join(" · ")}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-slate-400">
                      {room.player_count}/{room.config.player_count}
                    </span>
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-medium ${
                        room.status === "waiting"
                          ? "bg-yellow-500/20 text-yellow-400"
                          : room.status === "playing"
                          ? "bg-green-500/20 text-green-400"
                          : "bg-slate-500/20 text-slate-400"
                      }`}
                    >
                      {room.status === "waiting"
                        ? "等待中"
                        : room.status === "playing"
                        ? "进行中"
                        : "已结束"}
                    </span>
                  </div>
                </div>
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
