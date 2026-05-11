import { NextRequest, NextResponse } from "next/server";
import { checkAuth } from "../../actions";

const apiUrl = (
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001"
).replace(/\/+$/, "");

async function proxyRequest(
  req: NextRequest,
  method: string,
): Promise<NextResponse> {
  if (!(await checkAuth())) {
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
