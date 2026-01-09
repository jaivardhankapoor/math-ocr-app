import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function updateUserTier(
  userId: string,
  tier: string,
  stripeCustomerId: string | null,
  stripeSubscriptionId: string | null
) {
  const jose = await import("jose");
  const secret = new TextEncoder().encode(process.env.NEXTAUTH_SECRET!);

  const token = await new jose.SignJWT({
    sub: userId,
    email: "",
    name: "",
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 3600,
  })
    .setProtectedHeader({ alg: "HS256" })
    .sign(secret);

  const response = await fetch(`${API_URL}/users/${userId}/tier`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      tier,
      stripe_customer_id: stripeCustomerId,
      stripe_subscription_id: stripeSubscriptionId,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to update user tier: ${await response.text()}`);
  }
}

export async function POST(req: NextRequest) {
  const body = await req.text();
  const sig = req.headers.get("stripe-signature");

  if (!sig) {
    return NextResponse.json(
      { error: "No signature" },
      { status: 400 }
    );
  }

  const stripeSecretKey = process.env.STRIPE_SECRET_KEY;
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

  if (!stripeSecretKey || !webhookSecret) {
    return NextResponse.json(
      { error: "Stripe not configured" },
      { status: 500 }
    );
  }

  const stripe = new Stripe(stripeSecretKey, {
    apiVersion: "2025-12-15.clover",
  });

  let event: Stripe.Event;

  try {
    event = stripe.webhooks.constructEvent(
      body,
      sig,
      webhookSecret
    );
  } catch (err) {
    console.error("Webhook signature verification failed:", err);
    return NextResponse.json(
      { error: "Invalid signature" },
      { status: 400 }
    );
  }

  try {
    switch (event.type) {
      case "checkout.session.completed": {
        const session = event.data.object as Stripe.Checkout.Session;
        const userId = session.metadata?.userId || session.client_reference_id;

        if (userId && session.customer && session.subscription) {
          await updateUserTier(
            userId,
            "paid",
            session.customer as string,
            session.subscription as string
          );
          console.log(`User ${userId} upgraded to paid tier`);
        }
        break;
      }

      case "customer.subscription.deleted": {
        const subscription = event.data.object as Stripe.Subscription;
        const customer = subscription.customer as string;

        const sessions = await stripe.checkout.sessions.list({
          customer,
          limit: 1,
        });

        const userId = sessions.data[0]?.metadata?.userId || sessions.data[0]?.client_reference_id;

        if (userId) {
          await updateUserTier(userId, "free", customer, null);
          console.log(`User ${userId} downgraded to free tier`);
        }
        break;
      }

      case "customer.subscription.updated": {
        const subscription = event.data.object as Stripe.Subscription;
        const customer = subscription.customer as string;

        const sessions = await stripe.checkout.sessions.list({
          customer,
          limit: 1,
        });

        const userId = sessions.data[0]?.metadata?.userId || sessions.data[0]?.client_reference_id;

        if (userId) {
          const tier = subscription.status === "active" ? "paid" : "free";
          await updateUserTier(
            userId,
            tier,
            customer,
            subscription.status === "active" ? subscription.id : null
          );
          console.log(`User ${userId} subscription updated to ${tier}`);
        }
        break;
      }
    }

    return NextResponse.json({ received: true });
  } catch (error) {
    console.error("Webhook handler error:", error);
    return NextResponse.json(
      { error: "Webhook handler failed" },
      { status: 500 }
    );
  }
}
