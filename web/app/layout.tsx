import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import Chrome from "@/components/Chrome";
import { AuthProvider } from "@/lib/auth";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin", "cyrillic"] });

export const metadata: Metadata = {
  title: "MedPrice.kz - сравнение цен на медуслуги в Казахстане",
  description:
    "Агрегатор цен на анализы, МРТ, КТ, УЗИ и приёмы врачей по клиникам Казахстана. Сравните стоимость одной услуги в десятках клиник и найдите дешевле.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru" className={`${geistSans.variable} h-full`}>
      <body className="flex min-h-full flex-col antialiased">
        <AuthProvider>
          <Chrome>{children}</Chrome>
        </AuthProvider>
      </body>
    </html>
  );
}
