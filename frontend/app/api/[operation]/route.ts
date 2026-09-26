import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

// Fixed destinations only; admin credentials are forwarded solely to /v1/admin.
export async function POST(
  request: NextRequest,
  context: { params: Promise<{ operation: string }> },
) {
  const { operation } = await context.params;
  if (!["query", "retrieve", "admin"].includes(operation)) {
    return NextResponse.json({ detail: "Unknown operation" }, { status: 404 });
  }
  const headers = { "Cache-Control": "no-store" };
  // nextUrl may normalize 127.0.0.1 to localhost; Host preserves the browser's
  // authority (including a forwarded local SSH port). Do not trust X-Forwarded-Host.
  const browserOrigin = `${request.nextUrl.protocol}//${request.headers.get("host")}`;
  if (
    request.headers.get("origin") &&
    request.headers.get("origin") !== browserOrigin
  ) {
    return NextResponse.json(
      { detail: "Cross-origin requests are not allowed" },
      { status: 403, headers },
    );
  }
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return NextResponse.json(
      { detail: "Expected JSON" },
      { status: 415, headers },
    );
  }
  try {
    const body = await request.text();
    if (new TextEncoder().encode(body).length > 32768) {
      return NextResponse.json(
        { detail: "Request too large" },
        { status: 413, headers },
      );
    }
    try {
      JSON.parse(body);
    } catch {
      return NextResponse.json(
        { detail: "Invalid JSON" },
        { status: 400, headers },
      );
    }
    const base = new URL(
      process.env.TAXGUIDE_API_URL || "http://127.0.0.1:8000",
    );
    if (
      !["http:", "https:"].includes(base.protocol) ||
      base.username ||
      base.password
    )
      throw new Error("Invalid configuration");
    const upstream = await fetch(new URL(`/v1/${operation}`, base), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(operation === "admin"
          ? { Authorization: request.headers.get("authorization") || "" }
          : {}),
      },
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(180000),
    });
    const responseHeaders = new Headers(headers);
    for (const name of ["x-request-id", "x-trace-id", "traceparent"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return NextResponse.json(await upstream.json(), {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      { detail: "TaxGuide API unavailable" },
      { status: 502, headers },
    );
  }
}
