import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Karaoke Manager",
  description: "Search, fetch, and manage karaoke videos",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen">
        <nav className="border-b border-gray-800 px-6 py-4">
          <div className="max-w-7xl mx-auto flex items-center gap-3">
            <span className="text-xl font-bold">Karaoke Manager</span>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
