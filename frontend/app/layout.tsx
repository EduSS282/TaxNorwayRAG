import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "TaxGuide Norway",
  description: "Norwegian tax questions grounded in official evidence.",
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
