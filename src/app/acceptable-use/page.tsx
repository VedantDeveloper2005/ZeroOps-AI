import type { Metadata } from "next";
import { PolicyPage } from "@/components/public/PolicyPage";
import { publicPages } from "@/components/public/publicContent";

export const metadata: Metadata = {
  title: "Acceptable Use Policy",
  description:
    "Baseline rules for authorized, safe use of ZeroOps AI repositories, workers, and connected Azure accounts.",
};

export default function AcceptableUsePage() {
  return <PolicyPage {...publicPages.acceptableUse} />;
}
