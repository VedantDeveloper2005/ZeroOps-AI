import type { Metadata } from "next";
import { PolicyPage } from "@/components/public/PolicyPage";
import { publicPages } from "@/components/public/publicContent";

export const metadata: Metadata = {
  title: "Cookie Policy",
  description:
    "The necessary session, request-protection, OAuth, and verification cookies used by ZeroOps AI.",
};

export default function CookiesPage() {
  return <PolicyPage {...publicPages.cookies} />;
}
