"use server";

import { cookies } from "next/headers";

import crypto from "crypto";

const PASSWORD = process.env.DASHBOARD_PASSWORD || "";
const COOKIE_NAME = "predictions_auth";
// Use a secure server-side hash so attackers cannot manually guess and forge the cookie
const COOKIE_VALUE = crypto
  .createHash("sha256")
  .update(PASSWORD + "salt123")
  .digest("hex");

export async function login(password: string): Promise<{ success: boolean }> {
  if (password === PASSWORD) {
    const cookieStore = await cookies();
    cookieStore.set(COOKIE_NAME, COOKIE_VALUE, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 30, // 30 days
      path: "/",
    });
    return { success: true };
  }
  return { success: false };
}

export async function checkAuth(): Promise<boolean> {
  const cookieStore = await cookies();
  return cookieStore.get(COOKIE_NAME)?.value === COOKIE_VALUE;
}

export async function logout(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(COOKIE_NAME);
}

export async function updateConfig(
  key: string,
  value: string,
): Promise<{ success: boolean; error?: string }> {
  const isAuthed = await checkAuth();
  if (!isAuthed) return { success: false, error: "Authentication required" };

  const apiUrl = (
    process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001"
  ).replace(/\/+$/, "");
  const res = await fetch(`${apiUrl}/api/config`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.API_TOKEN || ""}`,
    },
    body: JSON.stringify({ key, value }),
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => "unknown");
    return {
      success: false,
      error: `backend returned ${res.status}: ${txt} | token used: ${process.env.API_TOKEN ? "yes" : "no"}`,
    };
  }

  return { success: true };
}
