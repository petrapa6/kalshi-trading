import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME, COOKIE_VALUE } from "../../auth";

// API_URL (no NEXT_PUBLIC_ prefix) is read at runtime so run.sh can point the
// proxy at the loopback API in the HAOS container. NEXT_PUBLIC_API_URL is baked
// at build time (SST/local-dev set it); the runtime API_URL takes precedence.
const apiUrl = (
  process.env.API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8001"
).replace(/\/+$/, "");

async function proxyRequest(
  req: NextRequest,
  method: string,
): Promise<NextResponse> {
  // Read the session cookie from the request directly. Calling the "use server"
  // checkAuth() here returns false in Next 16 standalone (no cookie context).
  if (req.cookies.get(COOKIE_NAME)?.value !== COOKIE_VALUE) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const targetUrl = new URL(req.url);
  const backendUrl = `${apiUrl}${targetUrl.pathname}${targetUrl.search}`;

  try {
    const body =
      method !== "GET" && method !== "DELETE" ? await req.text() : undefined;
    const res = await fetch(backendUrl, {
      method,
      headers: {
        Authorization: `Bearer ${process.env.API_TOKEN || ""}`,
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body,
      cache: "no-store",
    });

    const contentType = res.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      const data = await res.json();
      return NextResponse.json(data, { status: res.status });
    }

    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { "Content-Type": contentType || "text/plain" },
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

export async function GET(req: NextRequest) {
  return proxyRequest(req, "GET");
}
export async function POST(req: NextRequest) {
  return proxyRequest(req, "POST");
}
export async function PUT(req: NextRequest) {
  return proxyRequest(req, "PUT");
}
export async function DELETE(req: NextRequest) {
  return proxyRequest(req, "DELETE");
}
