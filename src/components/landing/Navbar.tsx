"use client";

import { useState } from "react";
import { motion, useScroll, useTransform, AnimatePresence } from "framer-motion";
import { Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import Link from "next/link";

const navLinks = [
  { label: "Features", href: "#features" },
  { label: "Pricing", href: "#pricing" },
  { label: "Docs", href: "#docs" },
  { label: "Blog", href: "#blog" },
];

export default function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { scrollY } = useScroll();

  const bgOpacity = useTransform(scrollY, [0, 100], [0.02, 0.06]);
  const borderOpacity = useTransform(scrollY, [0, 100], [0.06, 0.12]);
  const blur = useTransform(scrollY, [0, 100], [12, 24]);

  return (
    <motion.header
      className="fixed top-0 left-0 right-0 z-50 flex justify-center px-4 pt-4"
      initial={{ y: -80, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
    >
      <motion.nav
        className="w-full max-w-6xl rounded-2xl px-6 py-3 flex items-center justify-between"
        style={{
          background: useTransform(bgOpacity, (v) => `rgba(var(--glass-base-rgb), ${v})`),
          borderWidth: 1,
          borderStyle: "solid",
          borderColor: useTransform(borderOpacity, (v) => `rgba(var(--glass-base-rgb), ${v})`),
          backdropFilter: useTransform(blur, (v) => `blur(${v}px)`),
          WebkitBackdropFilter: useTransform(blur, (v) => `blur(${v}px)`),
        }}
      >
        {/* Logo */}
        <a href="#" className="flex items-center gap-2.5 group">
          <div className="relative w-9 h-9 flex items-center justify-center">
            <svg
              viewBox="0 0 40 40"
              fill="none"
              className="w-9 h-9"
              xmlns="http://www.w3.org/2000/svg"
            >
              {/* Outer hexagon */}
              <path
                d="M20 2L36.66 11.5V30.5L20 40L3.34 30.5V11.5L20 2Z"
                stroke="url(#logo-gradient)"
                strokeWidth="1.5"
                fill="none"
                className="group-hover:stroke-[2] transition-all duration-300"
              />
              {/* Inner circuit lines */}
              <path
                d="M20 10L28 15V25L20 30L12 25V15L20 10Z"
                stroke="url(#logo-gradient)"
                strokeWidth="1.2"
                fill="rgba(59,130,246,0.08)"
              />
              {/* Center node */}
              <circle cx="20" cy="20" r="2.5" fill="url(#logo-gradient)" />
              {/* Circuit connections */}
              <line x1="20" y1="10" x2="20" y2="17.5" stroke="url(#logo-gradient)" strokeWidth="1" opacity="0.6" />
              <line x1="28" y1="25" x2="22.5" y2="20" stroke="url(#logo-gradient)" strokeWidth="1" opacity="0.6" />
              <line x1="12" y1="25" x2="17.5" y2="20" stroke="url(#logo-gradient)" strokeWidth="1" opacity="0.6" />
              <defs>
                <linearGradient id="logo-gradient" x1="3" y1="2" x2="37" y2="40">
                  <stop stopColor="#3b82f6" />
                  <stop offset="1" stopColor="#8b5cf6" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <span className="text-lg font-bold tracking-tight text-foreground">
            Zero<span className="gradient-text">Ops</span>
          </span>
        </a>

        {/* Center nav links — desktop */}
        <div className="hidden md:flex items-center gap-1">
          {navLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="px-4 py-2 text-sm font-medium text-foreground-muted hover:text-foreground transition-colors duration-200 rounded-lg hover:bg-white/[0.04]"
            >
              {link.label}
            </a>
          ))}
        </div>

        {/* Right actions */}
        <div className="hidden md:flex items-center gap-3">
          <Link
            href="/login"
            className="px-4 py-2 text-sm font-medium text-foreground-muted hover:text-foreground transition-colors duration-200"
          >
            Sign In
          </Link>
          <Link
            href="/signup"
            className={cn(
              "relative px-5 py-2.5 text-sm font-semibold rounded-xl",
              "bg-primary text-white glow-blue",
              "hover:bg-primary-hover transition-all duration-300",
              "overflow-hidden group"
            )}
          >
            {/* Animated shine sweep */}
            <span className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-700 ease-out bg-gradient-to-r from-transparent via-white/20 to-transparent" />
            <span className="relative">Start Deploying</span>
          </Link>
        </div>

        {/* Mobile hamburger */}
        <button
          className="md:hidden p-2 text-foreground-muted hover:text-foreground transition-colors"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle menu"
        >
          {mobileOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
      </motion.nav>

      {/* Mobile menu */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            className="absolute top-full left-4 right-4 mt-2 rounded-2xl glass p-4 md:hidden"
            initial={{ opacity: 0, y: -10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.98 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="flex flex-col gap-1">
              {navLinks.map((link, i) => (
                <motion.a
                  key={link.label}
                  href={link.href}
                  className="px-4 py-3 text-sm font-medium text-foreground-muted hover:text-foreground hover:bg-white/[0.04] rounded-lg transition-colors"
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                  onClick={() => setMobileOpen(false)}
                >
                  {link.label}
                </motion.a>
              ))}
              <div className="border-t border-border my-2" />
              <Link
                href="/login"
                className="px-4 py-3 text-sm font-medium text-foreground-muted hover:text-foreground rounded-lg transition-colors"
                onClick={() => setMobileOpen(false)}
              >
                Sign In
              </Link>
              <Link
                href="/signup"
                className="px-4 py-3 text-sm font-semibold text-white bg-primary rounded-xl text-center glow-blue"
                onClick={() => setMobileOpen(false)}
              >
                Start Deploying
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  );
}
