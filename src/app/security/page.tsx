import type { Metadata } from "next";
import { PolicyPage } from "@/components/public/PolicyPage";
import { publicPages } from "@/components/public/publicContent";

export const metadata: Metadata = {
  title: "Security",
  description:
    "A factual overview of ZeroOps AI authentication, approval, secret-handling, upload, and deployment-worker controls.",
};

export default function SecurityPage() {
  return <PolicyPage {...publicPages.security} />;
}
