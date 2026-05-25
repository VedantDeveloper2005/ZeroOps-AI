import Navbar from "@/components/landing/Navbar";
import { HeroSection } from "@/components/landing/HeroSection";
import { FeaturesSection } from "@/components/landing/FeaturesSection";
import { DeploymentFlowSection } from "@/components/landing/DeploymentFlowSection";
import { SecuritySection } from "@/components/landing/SecuritySection";
import { AIIntelligenceSection } from "@/components/landing/AIIntelligenceSection";
import { AutonomousShowcaseSection } from "@/components/landing/AutonomousShowcaseSection";
import { MetricsSection } from "@/components/landing/MetricsSection";
import { PricingSection } from "@/components/landing/PricingSection";
import { Footer } from "@/components/landing/Footer";

export default function Home() {
  return (
    <main className="overflow-x-hidden">
      <Navbar />
      <HeroSection />
      <FeaturesSection />
      <DeploymentFlowSection />
      <SecuritySection />
      <AIIntelligenceSection />
      <AutonomousShowcaseSection />
      <MetricsSection />
      <PricingSection />
      <Footer />
    </main>
  );
}
