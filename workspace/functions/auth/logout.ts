import { clearCookieHeader } from "../../src/lib/session";

export const onRequestGet: PagesFunction = async ({ request }) => {
  const url = new URL(request.url);
  return new Response(null, {
    status: 302,
    headers: {
      Location: new URL("/", url.origin).toString(),
      "Set-Cookie": clearCookieHeader(),
      "Cache-Control": "private, no-store",
    },
  });
};
