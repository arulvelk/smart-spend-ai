import { forward } from "@/lib/server-api";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: Request, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}

export async function POST(req: Request, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}
