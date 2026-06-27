"use client";

import { useParams } from "next/navigation";
import ClinicDetail from "@/components/ClinicDetail";

export default function AdminClinicCardPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  return <ClinicDetail id={id} backHref="/admin/clinics" backLabel="к списку клиник" />;
}
