import type { Metadata } from "next";
import { PolicyPage } from "@/components/public/PolicyPage";
import { publicPages } from "@/components/public/publicContent";

export const metadata: Metadata = {
  title: "Data Processing and Retention",
  description:
    "How ZeroOps AI processes source, account, infrastructure, deployment, log, and monitoring data, plus open DPA decisions.",
};

export default function DataProcessingPage() {
  return <PolicyPage {...publicPages.dataProcessing} />;
}
