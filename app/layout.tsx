import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Math OCR - PDF to LaTeX",
  description: "Convert handwritten math notes to LaTeX using Gemini 3 Flash",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased bg-gray-50 dark:bg-gray-900">{children}</body>
    </html>
  );
}
