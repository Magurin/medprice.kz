import { revalidateTag } from "next/cache";
import { NextRequest, NextResponse } from "next/server";

// Точечная чистка кэша каталога после фонового обновления цен (раз в сутки).
// Вызывается из GitHub Actions после refresh-задачи:
//   curl -X POST "https://<домен>/api/revalidate?secret=$REVALIDATE_SECRET"
// Если REVALIDATE_SECRET не задан в окружении - эндпоинт выключен (503),
// а кэш всё равно сам обновится по таймеру (revalidate = 24ч).
export async function POST(req: NextRequest) {
  const secret = process.env.REVALIDATE_SECRET;
  if (!secret) {
    return NextResponse.json({ ok: false, error: "disabled" }, { status: 503 });
  }
  if (req.nextUrl.searchParams.get("secret") !== secret) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }
  revalidateTag("catalog", "max");
  return NextResponse.json({ ok: true, revalidated: "catalog" });
}
