import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Calibration Trending System",
  description: "Accredited Metrology Standards Laboratory Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased bg-[#f6f8fb] text-[#0b1329] font-sans">
        {children}
      </body>
    </html>
  );
}