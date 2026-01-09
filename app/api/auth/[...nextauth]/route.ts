import NextAuth, { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import { JWT } from "next-auth/jwt";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
  session: {
    strategy: "jwt",
  },
  secret: process.env.NEXTAUTH_SECRET,
  callbacks: {
    async jwt({ token, user, account }) {
      if (user) {
        token.sub = user.id;
        token.email = user.email;
        token.name = user.name || undefined;
        token.picture = user.image || undefined;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.sub as string;
        session.user.email = token.email as string;
        session.user.name = token.name as string;
        session.user.image = token.picture as string;
      }
      return session;
    },
    async signIn({ user, account }) {
      if (!user.email || !user.id) {
        return false;
      }

      try {
        const token = await createJWT({
          sub: user.id,
          email: user.email,
          name: user.name || "",
          picture: user.image || "",
        });

        const response = await fetch(`${API_URL}/users/sync`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            id: user.id,
            email: user.email,
            name: user.name,
            image: user.image,
          }),
        });

        if (!response.ok) {
          console.error("Failed to sync user:", await response.text());
          return false;
        }

        return true;
      } catch (error) {
        console.error("Error syncing user:", error);
        return false;
      }
    },
  },
};

async function createJWT(payload: {
  sub: string;
  email: string;
  name: string;
  picture: string;
}): Promise<string> {
  const jose = await import("jose");
  const secret = new TextEncoder().encode(process.env.NEXTAUTH_SECRET!);

  const jwt = await new jose.SignJWT({
    ...payload,
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 3600,
  })
    .setProtectedHeader({ alg: "HS256" })
    .sign(secret);

  return jwt;
}

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
