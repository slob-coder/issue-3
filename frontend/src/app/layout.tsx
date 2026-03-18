import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Werewolf Arena - AI Agent 狼人杀",
  description: "AI Agent Werewolf Game Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
