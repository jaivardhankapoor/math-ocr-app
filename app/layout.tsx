import type { Metadata } from "next";
import "./globals.css";
import SessionProvider from "./components/SessionProvider";
import AuthButton from "./components/AuthButton";

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
      <body className="antialiased bg-gray-50 dark:bg-gray-900">
        <SessionProvider>
          <div className="min-h-screen flex flex-col">
            <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
              <div className="container mx-auto px-4 py-4 flex justify-between items-center">
                <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                  Math OCR
                </h1>
                <AuthButton />
              </div>
            </header>
            <main className="flex-1">{children}</main>
          </div>
        </SessionProvider>
      </body>
    </html>
  );
}
