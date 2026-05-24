import crypto from "crypto";

// Shared auth constants. Kept out of actions.ts because that file is
// "use server" (can only export async functions), and Route Handlers that
// call a "use server" function don't share its cookie context in Next 16 —
// so the proxy route reads req.cookies directly using these constants.
export const COOKIE_NAME = "predictions_auth";

// Secure server-side hash so attackers cannot manually guess and forge the cookie.
export const COOKIE_VALUE = crypto
  .createHash("sha256")
  .update((process.env.DASHBOARD_PASSWORD || "") + "salt123")
  .digest("hex");
