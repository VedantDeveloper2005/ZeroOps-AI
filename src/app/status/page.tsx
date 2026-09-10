import type { Metadata } from "next";
import { PolicyPage } from "@/components/public/PolicyPage";
import { publicPages } from "@/components/public/publicContent";

export const metadata: Metadata = {
  title: "Service Status",
  description:
    "ZeroOps AI public status placeholder, shown without an invented healthy state while no verified feed is connected.",
  robots: { index: false, follow: false, nocache: true },
};

export default function StatusPage() {
  return <PolicyPage {...publicPages.status} />;
}
