/**
 * API client for the frontend.
 */

const BASE_URL = "/api/v1";

export async function fetchRooms(status?: string) {
  const params = status ? `?status=${status}` : "";
  const res = await fetch(`${BASE_URL}/rooms${params}`);
  return res.json();
}

export async function fetchRoom(roomId: string) {
  const res = await fetch(`${BASE_URL}/rooms/${roomId}`);
  return res.json();
}

export async function fetchRoomState(roomId: string) {
  const res = await fetch(`${BASE_URL}/rooms/${roomId}/state`);
  return res.json();
}

export async function fetchReplay(roomId: string) {
  const res = await fetch(`${BASE_URL}/rooms/${roomId}/replay`);
  return res.json();
}

export async function fetchRoomHistory(roomId: string) {
  const res = await fetch(`${BASE_URL}/rooms/${roomId}/history`);
  return res.json();
}
