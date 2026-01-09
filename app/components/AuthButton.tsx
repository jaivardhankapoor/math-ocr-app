"use client";

import { signIn, signOut, useSession } from "next-auth/react";

export default function AuthButton() {
  const { data: session, status } = useSession();

  if (status === "loading") {
    return (
      <button
        disabled
        className="px-4 py-2 bg-gray-300 text-gray-600 rounded cursor-not-allowed"
      >
        Loading...
      </button>
    );
  }

  if (session?.user) {
    return (
      <div className="flex items-center gap-4">
        {session.user.image && (
          <img
            src={session.user.image}
            alt={session.user.name || "User"}
            className="w-8 h-8 rounded-full"
          />
        )}
        <span className="text-sm text-gray-700">
          {session.user.email}
        </span>
        <button
          onClick={() => signOut()}
          className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600"
        >
          Sign Out
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => signIn("google")}
      className="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 font-medium"
    >
      Sign in with Google
    </button>
  );
}
