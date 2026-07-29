import type { Metadata } from "next";
import { PolicyPage } from "@/components/public/PolicyPage";
import { publicPages } from "@/components/public/publicContent";

export const metadata: Metadata = {
  title: "Contact",
  description:
    "Routing guidance for ZeroOps AI product, account, privacy, legal, incident, and security questions.",
};

export default function ContactPage() {
  return <PolicyPage {...publicPages.contact} />;
}
