import { useState } from "react";
import { mutate } from "swr";
import { useTheme } from "next-themes";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Sparkles,
  Folder,
  Palette,
  Sun,
  Moon,
  LogOut,
  Key,
  Menu,
  X,
  User,
} from "lucide-react";
import { authApi } from "../apis/auth";
import { useAuthStore } from "../store/authStore";
import { useResumeStore } from "../store/resumeStore";
import { AnalyzeView } from "../views/AnalyzeView";
import { GlobalJobToasts } from "./GlobalJobToasts";

import { AnimatePresence, motion } from "framer-motion";

import { NavItem } from "./NavItem";

export function AppLayout() {
  const { theme, setTheme } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const isDark = theme === "dark";
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch (e) {
      // Ignore errors on logout
    }
    // Clear local Zustand state
    useAuthStore.getState().logout();
    useResumeStore.getState().resetResumeState();

    // Clear all SWR caches (profiles, library, api keys)
    mutate(() => true, undefined, { revalidate: false });

    navigate("/login");
  };

  const closeSidebar = () => setIsSidebarOpen(false);

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      {/* Mobile backdrop */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-xs md:hidden"
          onClick={closeSidebar}
        />
      )}

      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-60 bg-background flex flex-col transition-transform duration-300 ease-in-out md:static md:translate-x-0 ${
          isSidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand */}
        <div className="px-5 py-5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-heading text-[32px] text-sidebar-foreground font-bold leading-tight">
              Resume
              <br />
              <span className="text-primary font-sans font-semibold text-xl tracking-widest uppercase">
                Reworker
              </span>
            </span>
          </div>
          <button
            onClick={closeSidebar}
            className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground md:hidden"
            aria-label="Close sidebar"
          >
            <X size={18} />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 flex flex-col gap-1">
          <NavItem
            to="/analyze"
            icon={<Sparkles size={16} />}
            onClick={closeSidebar}
          >
            New Analysis
          </NavItem>
          <NavItem
            to="/library"
            icon={<Folder size={16} />}
            onClick={closeSidebar}
          >
            My Library
          </NavItem>
          <NavItem
            to="/templates"
            icon={<Palette size={16} />}
            onClick={closeSidebar}
          >
            My Templates
          </NavItem>
          <NavItem
            to="/apikeys"
            icon={<Key size={16} />}
            onClick={closeSidebar}
          >
            API Keys
          </NavItem>
          <NavItem
            to="/profile"
            icon={<User size={16} />}
            onClick={closeSidebar}
          >
            My Profile
          </NavItem>
        </nav>

        {/* Footer: dark mode toggle */}
        <div className="px-4 py-4">
          <button
            onClick={() => setTheme(isDark ? "light" : "dark")}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            {isDark ? <Sun size={16} /> : <Moon size={16} />}
            {isDark ? "Light Mode" : "Dark Mode"}
          </button>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2 mt-1 rounded-lg text-sm text-red-500 hover:bg-red-500/10 transition-colors"
          >
            <LogOut size={16} />
            Sign Out
          </button>
        </div>
      </aside>

      {/* ── Main ─────────────────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 min-h-0 bg-background relative z-0 overflow-hidden">
        {/* Mobile Header Bar */}
        <header className="flex md:hidden items-center justify-between px-4 py-3 border-b border-border bg-background shrink-0">
          <button
            onClick={() => setIsSidebarOpen(true)}
            className="p-2 rounded-lg hover:bg-muted text-muted-foreground"
            aria-label="Open sidebar"
          >
            <Menu size={20} />
          </button>
          <span className="font-heading text-xl font-bold text-foreground">
            Resume Reworker
          </span>
          <div className="w-9" /> {/* Spacer to balance the layout */}
        </header>

        <div
          className={`flex-1 flex flex-col min-h-0 h-full w-full ${location.pathname === "/analyze" ? "" : "hidden"}`}
        >
          <AnalyzeView />
        </div>
        {location.pathname !== "/analyze" && (
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, filter: "blur(4px)" }}
              animate={{ opacity: 1, filter: "blur(0px)" }}
              exit={{ opacity: 0, filter: "blur(4px)" }}
              transition={{ duration: 0.2, ease: "easeInOut" }}
              className="flex-1 flex flex-col min-h-0 h-full w-full overflow-y-auto"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        )}
      </main>

      {/* Global style-change job notifications — persists across page navigation */}
      <GlobalJobToasts />
    </div>
  );
}
