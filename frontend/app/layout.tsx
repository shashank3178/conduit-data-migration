import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Snowbridge | Database Migration",
  description: "Discover, plan and migrate enterprise databases."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
