import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Anthropic",
  description:
    "Anthropic is an AI safety and research company building reliable and steerable AI systems.",
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
