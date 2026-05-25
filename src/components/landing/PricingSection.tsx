"use client";

import { useState } from "react";
import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { Check } from "lucide-react";
import { pricingPlans } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

export function PricingSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.2 });
  const [yearly, setYearly] = useState(false);

  return (
    <section ref={ref} className="py-24 px-4" id="pricing">
      <div className="max-w-6xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={isInView ? { opacity: 1, y: 0 } : {}} transition={{ duration: 0.6 }} className="text-center mb-12">
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            Simple, <span className="gradient-text">Transparent Pricing</span>
          </h2>
          <p className="text-foreground-muted text-lg max-w-xl mx-auto mb-8">Start free. Scale as you grow. No hidden fees.</p>

          {/* Toggle */}
          <div className="flex items-center justify-center gap-3">
            <span className={cn("text-sm", !yearly ? "text-foreground" : "text-foreground-muted")}>Monthly</span>
            <button onClick={() => setYearly(!yearly)} className={cn("w-12 h-6 rounded-full relative transition-colors", yearly ? "bg-primary" : "bg-card border border-border")}>
              <motion.div className="w-5 h-5 rounded-full bg-white absolute top-0.5" animate={{ left: yearly ? 26 : 2 }} transition={{ type: "spring", stiffness: 500, damping: 30 }} />
            </button>
            <span className={cn("text-sm", yearly ? "text-foreground" : "text-foreground-muted")}>Yearly</span>
            {yearly && <span className="text-xs bg-success/10 text-success px-2 py-0.5 rounded-full">Save 20%</span>}
          </div>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-6">
          {pricingPlans.map((plan, i) => (
            <motion.div key={plan.name} initial={{ opacity: 0, y: 30 }} animate={isInView ? { opacity: 1, y: 0 } : {}} transition={{ delay: i * 0.15, duration: 0.5 }}
              whileHover={{ y: -4 }}
              className={cn("glass rounded-2xl p-8 relative flex flex-col !overflow-visible",
                plan.highlighted && "border-primary/30 glow-blue scale-[1.02] z-10"
              )}>
              {plan.highlighted && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary text-white text-xs font-semibold px-4 py-1 rounded-full">
                  Most Popular
                </div>
              )}
              <h3 className="text-xl font-bold text-foreground">{plan.name}</h3>
              <div className="mt-4 mb-2">
                <span className="text-4xl font-bold text-foreground">{yearly ? plan.yearlyPrice : plan.price}</span>
                {plan.price !== "Custom" && <span className="text-foreground-muted text-sm">/month</span>}
              </div>
              <p className="text-sm text-foreground-muted mb-6">{plan.description}</p>

              <ul className="space-y-3 mb-8 flex-1">
                {plan.features.map(feature => (
                  <li key={feature} className="flex items-center gap-2 text-sm text-foreground">
                    <Check size={16} className="text-primary flex-shrink-0" />
                    {feature}
                  </li>
                ))}
              </ul>

              <button className={cn("w-full py-3 rounded-xl text-sm font-semibold transition-all",
                plan.highlighted
                  ? "bg-primary text-white hover:bg-primary-hover glow-blue"
                  : "glass border-border hover:border-border-hover text-foreground"
              )}>
                {plan.cta}
              </button>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
