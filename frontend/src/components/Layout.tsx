import { Link, NavLink, useLocation } from "react-router-dom";
import { Activity, Headphones } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/cx", label: "Customer Experience", icon: Headphones, exact: false },
  { to: "/operator", label: "Operator Console", icon: Activity, exact: false },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b bg-card">
        <div className="container flex h-14 items-center justify-between gap-6">
          <Link to="/" className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-md bg-primary text-primary-foreground grid place-items-center">
              <svg viewBox="0 0 20 16" className="h-4 w-5" fill="currentColor" aria-hidden>
                <rect x="1"  y="4" width="3" height="8"  rx="1.5" />
                <rect x="6"  y="1" width="3" height="14" rx="1.5" />
                <rect x="11" y="5" width="3" height="6"  rx="1.5" />
                <rect x="16" y="2" width="3" height="12" rx="1.5" />
              </svg>
            </div>
            <div className="font-semibold tracking-tight">ContactPulse</div>
          </Link>
          <nav className="flex items-center gap-1">
            {navItems.map(({ to, label, icon: Icon, exact }) => {
              const isActive = exact
                ? location.pathname === to
                : location.pathname.startsWith(to);
              return (
                <NavLink
                  key={to}
                  to={to}
                  className={cn(
                    "inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-secondary text-secondary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </NavLink>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="container py-6">{children}</main>
    </div>
  );
}
