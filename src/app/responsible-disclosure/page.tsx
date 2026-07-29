import type { Metadata } from "next";
import { PolicyPage } from "@/components/public/PolicyPage";
import { publicPages } from "@/components/public/publicContent";

export const metadata: Metadata = {
  title: "Responsible Disclosure",
  description:
    "Draft guidance for responsibly reporting a suspected ZeroOps AI security issue.",
};

export default function ResponsibleDisclosurePage() {
  return <PolicyPage {...publicPages.responsibleDisclosure} />;
}
