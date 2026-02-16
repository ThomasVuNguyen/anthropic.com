import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Anthropic V2 Rewrite",
  description: "Next.js rewrite workspace for anthropic.com-inspired design.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
