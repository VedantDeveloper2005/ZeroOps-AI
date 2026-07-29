import type { Metadata } from "next";
import { PolicyPage } from "@/components/public/PolicyPage";
import { publicPages } from "@/components/public/publicContent";

export const metadata: Metadata = {
  title: "Terms of Service",
  description:
    "Draft terms for ZeroOps AI accounts, repository access, infrastructure approvals, deployments, and cloud-provider charges.",
};

export default function TermsPage() {
  return <PolicyPage {...publicPages.terms} />;
}
