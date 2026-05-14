import type { Metadata } from "next";
import "./globals.css";


export const metadata: Metadata = {
  title: "Agent Core",
  description: "MiMo 模型集成的智能体平台控制台",
};


export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}