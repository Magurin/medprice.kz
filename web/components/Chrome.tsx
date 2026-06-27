"use client";

import { usePathname } from "next/navigation";
import Footer from "@/components/Footer";
import Header from "@/components/Header";

// На auth-маршрутах прячем общий хедер/футер - там свой полноэкранный layout.
const AUTH_ROUTES = ["/login", "/register"];

export default function Chrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isAuth = AUTH_ROUTES.some((r) => pathname === r || pathname.startsWith(r + "/"));

  if (isAuth) return <>{children}</>;

  return (
    <>
      <Header />
      <main className="flex-1">{children}</main>
      <Footer />
    </>
  );
}
