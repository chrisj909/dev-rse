import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "Real Estate Signal Engine",
  description: "Ranked seller and investor opportunities from public property data.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="flex h-screen overflow-hidden bg-gray-50 text-gray-900 antialiased">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-white pt-12 md:pt-0 pb-16 md:pb-0">
          {children}
        </main>
      </body>
    </html>
  );
}
