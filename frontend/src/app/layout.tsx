import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CONDUIT | Data Migration Workspace",
  description: "Plan, execute, monitor, and validate enterprise database migrations.",
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