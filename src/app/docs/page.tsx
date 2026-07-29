import type { Metadata } from "next";
import { PolicyPage } from "@/components/public/PolicyPage";
import { publicPages } from "@/components/public/publicContent";

export const metadata: Metadata = {
  title: "Documentation",
  description:
    "Use ZeroOps AI for source intake, deterministic analysis, App Service plan approval, worker deployment, logs, and metrics.",
};

export default function DocsPage() {
  return <PolicyPage {...publicPages.docs} />;
}
