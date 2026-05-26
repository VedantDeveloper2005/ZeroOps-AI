"use client";

<<<<<<< HEAD
import { motion, useInView } from "framer-motion";
=======
import { motion, useInView, useSpring, useMotionValue } from "framer-motion";
>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2
import { useRef, useEffect, useState } from "react";
import { Rocket, Clock, Zap, Server, Activity, Cpu } from "lucide-react";

const metrics = [
  { icon: Rocket, value: 10000, suffix: "+", label: "Deployments", color: "text-primary" },
  { icon: Clock, value: 99.99, suffix: "%", label: "Uptime", color: "text-success" },
  { icon: Zap, value: 50, suffix: "ms", label: "Avg Response", prefix: "<", color: "text-warning" },
  { icon: Server, value: 500, suffix: "+", label: "Active Clusters", color: "text-info" },
  { icon: Activity, value: 1000000, suffix: "+", label: "Scaling Events", color: "text-accent" },
  { icon: Cpu, value: 100, suffix: "+", label: "Deployments/min", color: "text-primary" },
];

function Counter({ value, suffix, prefix }: { value: number; suffix: string; prefix?: string }) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });
  const [display, setDisplay] = useState("0");

  useEffect(() => {
    if (!isInView) return;
    const duration = 2000;
    const startTime = performance.now();
    const animate = (time: number) => {
      const elapsed = time - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = eased * value;
      if (value >= 1000000) setDisplay(`${(current / 1000000).toFixed(current >= value ? 0 : 1)}M`);
      else if (value >= 1000) setDisplay(`${(current / 1000).toFixed(current >= value ? 0 : 1)}K`);
      else if (value % 1 !== 0) setDisplay(current.toFixed(2));
      else setDisplay(Math.floor(current).toString());
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, [isInView, value]);

  return <span ref={ref}>{prefix}{display}{suffix}</span>;
}

export function MetricsSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.2 });

  return (
    <section ref={ref} className="py-24 px-4">
      <div className="max-w-7xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={isInView ? { opacity: 1, y: 0 } : {}} transition={{ duration: 0.6 }} className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            Trusted by <span className="gradient-text">Engineering Teams</span> Worldwide
          </h2>
        </motion.div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {metrics.map((metric, i) => (
            <motion.div key={metric.label} initial={{ opacity: 0, y: 20 }} animate={isInView ? { opacity: 1, y: 0 } : {}} transition={{ delay: i * 0.1, duration: 0.5 }}
              whileHover={{ y: -4, boxShadow: "0 0 30px hsla(217, 91%, 60%, 0.1)" }}
              className="glass rounded-xl p-6 text-center group cursor-pointer">
              <metric.icon size={24} className={`${metric.color} mx-auto mb-3`} />
              <p className="text-3xl md:text-4xl font-bold text-foreground mb-1">
                <Counter value={metric.value} suffix={metric.suffix} prefix={metric.label === "Avg Response" ? "<" : undefined} />
              </p>
              <p className="text-sm text-foreground-muted">{metric.label}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
