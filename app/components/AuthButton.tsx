"use client";

import { signIn, signOut, useSession } from "next-auth/react";

export default function AuthButton() {
  const { data: session, status } = useSession();

  if (status === "loading") {
    return (
      <button
        disabled
        className="px-4 py-2 bg-stone-200 text-stone-500 rounded-full cursor-not-allowed text-sm"
      >
        Loading...
      </button>
    );
  }

  if (session?.user) {
    return (
      <div className="flex items-center gap-3">
        <span className="text-sm text-stone-600 hidden sm:inline">
          {session.user.email}
        </span>
        <button
          onClick={() => signOut()}
          className="px-4 py-2 rounded-full border border-stone-300 text-stone-700 text-sm hover:border-stone-400 hover:bg-stone-50"
        >
          Sign Out
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => signIn("google")}
      className="px-5 py-2 rounded-full bg-stone-900 text-white text-sm font-medium hover:bg-stone-800"
    >
      Sign in with Google
    </button>
  );
}
