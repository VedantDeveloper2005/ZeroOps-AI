import type { Metadata } from "next";
import { PolicyPage } from "@/components/public/PolicyPage";
import { publicPages } from "@/components/public/publicContent";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "How ZeroOps AI processes account, repository, deployment, log, and monitoring data, with clear legal placeholders.",
};

export default function PrivacyPage() {
  return <PolicyPage {...publicPages.privacy} />;
}
