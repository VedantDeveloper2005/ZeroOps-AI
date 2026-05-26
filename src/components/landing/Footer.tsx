import { GitBranch, ExternalLink, Link2 } from "lucide-react";

const links = {
  Product: ["Features", "Pricing", "Security", "Docs"],
  Resources: ["Blog", "Changelog", "Status", "API Reference"],
  Company: ["About", "Careers", "Contact", "Partners"],
  Legal: ["Privacy", "Terms", "SLA", "Compliance"],
};

export function Footer() {
  return (
    <footer className="border-t border-border relative">
      <div className="h-px w-full bg-gradient-to-r from-transparent via-primary/40 to-transparent absolute top-0" />
      <div className="max-w-7xl mx-auto px-4 py-16">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-8">
          {/* Brand */}
          <div className="col-span-2 md:col-span-1">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 2L21.5 7.5V16.5L12 22L2.5 16.5V7.5L12 2Z" stroke="white" strokeWidth="1.5" /><path d="M12 8L16 10.5V15.5L12 18L8 15.5V10.5L12 8Z" stroke="white" strokeWidth="1.5" fill="rgba(255,255,255,0.2)" /></svg>
              </div>
              <span className="text-lg font-bold">ZeroOps</span>
            </div>
            <p className="text-xs text-foreground-muted leading-relaxed mb-4">The operating system for autonomous cloud infrastructure.</p>
            <div className="flex gap-3">
              {[GitBranch, ExternalLink, Link2].map((Icon, i) => (
                <a key={i} href="#" className="w-8 h-8 rounded-lg glass-subtle flex items-center justify-center text-foreground-muted hover:text-foreground transition-colors">
                  <Icon size={16} />
                </a>
              ))}
            </div>
          </div>

          {/* Link columns */}
          {Object.entries(links).map(([title, items]) => (
            <div key={title}>
              <h4 className="text-sm font-semibold text-foreground mb-4">{title}</h4>
              <ul className="space-y-2.5">
                {items.map(item => (
                  <li key={item}><a href="#" className="text-sm text-foreground-muted hover:text-foreground transition-colors">{item}</a></li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="border-t border-border mt-12 pt-6 flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-xs text-foreground-muted">© 2026 ZeroOps. All rights reserved.</p>
          <p className="text-xs text-foreground-muted">Built for the future of cloud infrastructure.</p>
        </div>
      </div>
    </footer>
  );
}
