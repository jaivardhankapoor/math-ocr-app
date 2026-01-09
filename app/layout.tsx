import type { Metadata } from "next";
import { Roboto } from "next/font/google";
import "./globals.css";
import SessionProvider from "./components/SessionProvider";
import AuthButton from "./components/AuthButton";

const roboto = Roboto({
  subsets: ["latin"],
  weight: ["300", "400", "500", "700"],
  variable: "--font-sans",
});

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
      <body
        className={`${roboto.variable} min-h-screen antialiased text-stone-900 bg-[radial-gradient(1200px_600px_at_15%_-10%,_#f3efe8_0%,_#ffffff_48%,_#f2f7f6_100%)]`}
      >
        <SessionProvider>
          <div className="min-h-screen flex flex-col">
            <header className="bg-white/80 backdrop-blur border-b border-stone-200">
              <div className="max-w-5xl mx-auto px-6 py-4 flex justify-between items-center">
                <div className="flex items-center gap-3">
                  <div className="h-9 w-9 rounded-full bg-stone-900 text-white text-sm font-semibold flex items-center justify-center">
                    &Sigma;
                  </div>
                  <div>
                    <p className="text-base font-semibold tracking-tight">Math OCR</p>
                    <p className="text-xs text-stone-500">
                      Handwritten math to LaTeX
                    </p>
                  </div>
                </div>
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
