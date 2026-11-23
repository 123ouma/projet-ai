import type { Metadata } from "next";

import { ChatWindow } from "@/components/chat/chat-window";

export const metadata: Metadata = {
  title: "Assistant d'orientation | SmartCampus AI",
};

export default function Page() {
  return <ChatWindow />;
}
