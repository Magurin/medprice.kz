"use client";

import { useParams } from "next/navigation";
import ClinicDetail from "@/components/ClinicDetail";

export default function ClinicCardPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  return (
    <div className="mx-auto max-w-3xl px-4 py-7">
      <ClinicDetail id={id} backHref="/clinics" backLabel="к клиникам" />
    </div>
  );
}
