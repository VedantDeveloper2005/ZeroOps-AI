import type { Metadata } from "next";
import { PolicyPage } from "@/components/public/PolicyPage";
import { publicPages } from "@/components/public/publicContent";

export const metadata: Metadata = {
  title: "Third-Party Services and Subprocessors",
  description:
    "An implementation-based inventory of Azure, GitHub, and configured AI-provider processing in ZeroOps AI.",
};

export default function SubprocessorsPage() {
  return <PolicyPage {...publicPages.subprocessors} />;
}
