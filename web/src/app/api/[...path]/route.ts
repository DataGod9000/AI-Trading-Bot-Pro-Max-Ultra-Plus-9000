import { NextRequest, NextResponse } from "next/server";

/** Read backend URL on every request so Render runtime env works (no rebuild after changing API_PROXY_TARGET). */
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function backendBase(): string {
  const u =
    process.env.API_PROXY_TARGET?.trim() ||
    process.env.BACKEND_URL?.trim() ||
    process.env.NEXT_PUBLIC_API_URL?.trim() ||
    "";
  if (!u) {
    return "http://127.0.0.1:8000";
  }
  return u.replace(/\/$/, "");
}

async function proxy(req: NextRequest, segments: string[]) {
  const suffix = segments.length ? segments.join("/") : "";
  const target = `${backendBase()}/api/${suffix}${req.nextUrl.search}`;

  const headers = new Headers();
  for (const name of ["accept", "content-type", "authorization"]) {
    const v = req.headers.get(name);
    if (v) headers.set(name, v);
  }

  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
    redirect: "manual",
  };

  if (!["GET", "HEAD"].includes(req.method)) {
    init.body = await req.arrayBuffer();
  }

  let res: Response;
  try {
    res = await fetch(target, init);
  } catch (e) {
    console.error("[api proxy] fetch failed:", target, e);
    return NextResponse.json(
      {
        error: "Upstream unreachable",
        detail: String(e),
        hint: "Set API_PROXY_TARGET on this service to your FastAPI https URL (no trailing slash).",
      },
      { status: 502 },
    );
  }

  const out = new NextResponse(res.body, { status: res.status });
  const ct = res.headers.get("content-type");
  if (ct) out.headers.set("content-type", ct);
  return out;
}

type Ctx = { params: Promise<{ path?: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? []);
}

export async function POST(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? []);
}

export async function PUT(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? []);
}

export async function PATCH(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? []);
}

export async function DELETE(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? []);
}

export async function HEAD(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? []);
}
