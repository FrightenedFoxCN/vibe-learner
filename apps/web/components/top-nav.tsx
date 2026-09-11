"use client";

import { useEffect, useRef, useState } from "react";

import { BrandMark } from "./brand-mark";
import { MaterialIcon, type MaterialIconName } from "./material-icon";
import { AppLink, type AppRoutePath } from "../lib/app-navigation";
import {
  DESKTOP_VAULT_STATE_CHANGE_EVENT,
  isDesktopVaultCreationRequired
} from "../lib/desktop-vault";
import {
  APP_NAV_COLLAPSED_STORAGE_KEY,
  BROWSER_VIEW_TOGGLE_NAV_EVENT,
  readStoredBoolean,
  writeStoredBoolean
} from "../lib/view-preferences";

interface TopNavProps {
  currentPath: AppRoutePath;
}

const NAV_GROUPS: Array<{
  id: string;
  label: string;
  compactLabel: string;
  items: Array<{ href: AppRoutePath; label: string; icon: MaterialIconName }>;
}> = [
  { id: "learning", label: "学习", compactLabel: "学习", items: [
    { href: "/", label: "导航首页", icon: "home" },
    { href: "/plan", label: "计划生成", icon: "event_note" },
    { href: "/study", label: "章节对话", icon: "forum" },
  ] },
  { id: "world", label: "角色与世界", compactLabel: "世界", items: [
    { href: "/tavern", label: "角色酒馆", icon: "chat" },
    { href: "/persona-spectrum", label: "人格色谱", icon: "psychology_alt" },
    { href: "/scene-setup", label: "场景搭建", icon: "account_tree" },
    { href: "/sensory-tools", label: "感官工具", icon: "tune" },
  ] },
  { id: "system", label: "系统", compactLabel: "系统", items: [
    { href: "/settings", label: "统一设置", icon: "settings" },
    { href: "/model-usage", label: "用量审计", icon: "bar_chart" },
    { href: "/manual", label: "使用手册", icon: "menu_book" },
  ] },
];

export function TopNav({ currentPath }: TopNavProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const mobileToggle = useRef<HTMLButtonElement>(null);
  const desktopToggle = useRef<HTMLButtonElement>(null);
  const lastNavigationFocus = useRef<HTMLElement | null>(null);
  const navigation = useRef<HTMLElement>(null);
  const currentGroup = NAV_GROUPS.find((group) => group.items.some((item) => item.href === currentPath))!;
  const currentItem = currentGroup.items.find((item) => item.href === currentPath)!;

  useEffect(() => {
    setMobileOpen(false);
  }, [currentPath]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 760px)");
    const sync = () => {
      // CSS may hide the focused control before the media-query callback runs.
      const active = document.activeElement;
      const previous = lastNavigationFocus.current;
      const focused = active === document.body && previous && previous.getClientRects().length === 0
        ? previous : active;
      if (media.matches && (navigation.current?.contains(focused) || focused === desktopToggle.current)) {
        mobileToggle.current?.focus();
      } else if (!media.matches && focused === mobileToggle.current) {
        navigation.current?.querySelector<HTMLElement>('[aria-current="page"]')?.focus();
      }
      setMobileOpen(false);
    };
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  const [vaultCreationRequired, setVaultCreationRequired] = useState(false);

  useEffect(() => {
    setCollapsed(readStoredBoolean(APP_NAV_COLLAPSED_STORAGE_KEY));
  }, []);

  useEffect(() => {
    const syncVaultCreationRequirement = () => {
      setVaultCreationRequired(isDesktopVaultCreationRequired());
    };
    syncVaultCreationRequirement();
    window.addEventListener(DESKTOP_VAULT_STATE_CHANGE_EVENT, syncVaultCreationRequirement);
    return () => {
      window.removeEventListener(DESKTOP_VAULT_STATE_CHANGE_EVENT, syncVaultCreationRequirement);
    };
  }, []);

  useEffect(() => {
    const handleToggle = () => {
      if (window.matchMedia("(max-width: 760px)").matches) {
        if (mobileOpen && navigation.current?.contains(document.activeElement)) mobileToggle.current?.focus();
        setMobileOpen(!mobileOpen);
      } else {
        setCollapsed((value) => !value);
      }
    };
    window.addEventListener(BROWSER_VIEW_TOGGLE_NAV_EVENT, handleToggle);
    return () => {
      window.removeEventListener(BROWSER_VIEW_TOGGLE_NAV_EVENT, handleToggle);
    };
  }, [mobileOpen]);

  useEffect(() => {
    const width = collapsed ? "56px" : "200px";
    document.documentElement.style.setProperty("--app-nav-width", width);
    writeStoredBoolean(APP_NAV_COLLAPSED_STORAGE_KEY, collapsed);
  }, [collapsed]);

  return (
    <aside
      className={`app-side-nav${collapsed ? " is-collapsed" : ""}${mobileOpen ? " is-mobile-open" : ""}`}
      aria-label="Primary navigation"
      onKeyDown={(event) => {
        if (event.key === "Escape" && mobileOpen) {
          event.preventDefault();
          setMobileOpen(false);
          mobileToggle.current?.focus();
        }
      }}
      onFocusCapture={(event) => { lastNavigationFocus.current = event.target; }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          // An intentional move away clears the fallback; breakpoint hiding retains it.
          if (event.relatedTarget || event.target.getClientRects().length > 0) lastNavigationFocus.current = null;
          if (mobileOpen) setMobileOpen(false);
        }
      }}
    >
      <div className="app-nav-brand-row">
        <BrandMark size={28} />
        <span className="app-nav-brand-name">Vibe Learner</span>
      </div>
      <button
        ref={mobileToggle}
        type="button"
        className="app-nav-mobile-toggle"
        aria-expanded={mobileOpen}
        aria-controls="app-primary-links"
        onClick={() => setMobileOpen((value) => !value)}
      >
        <span className="app-nav-current">{currentGroup.label} · {currentItem.label}</span>
        <span>全部导航</span>
        <MaterialIcon name="expand_more" size={18} />
      </button>
      <nav ref={navigation} id="app-primary-links" className="app-nav-links" aria-label="主要导航">
        {NAV_GROUPS.map((group) => {
          const current = group.id === currentGroup.id;
          return (
            <div key={group.id} role="group" aria-label={`${group.label}${current ? "，当前分组" : ""}`} className="app-nav-group">
              <div className="app-nav-group-heading" aria-hidden="true" data-current={current} title={group.label}>
                <span className="app-nav-group-full">{group.label}</span>
                <span className="app-nav-group-compact">{group.compactLabel}</span>
                {current ? <span className="app-nav-group-current">当前</span> : null}
              </div>
              {group.items.map((item) => {
                const active = item.href === currentPath;
                const disabled = vaultCreationRequired && item.href !== "/settings";
                const content = <><MaterialIcon name={item.icon} size={18} /><span className="app-nav-label">{item.label}</span></>;
                return disabled ? (
                  <span key={item.href} className="app-nav-link" aria-disabled="true" aria-label={item.label} title="请先在统一设置创建桌面 Vault">{content}</span>
                ) : (
                  <AppLink
                    key={item.href}
                    path={item.href}
                    className={active ? "app-nav-link--active" : "app-nav-link"}
                    aria-label={item.label}
                    aria-current={active ? "page" : undefined}
                    title={item.label}
                    onClick={() => {
                      if (mobileOpen) mobileToggle.current?.focus();
                      setMobileOpen(false);
                    }}
                  >{content}</AppLink>
                );
              })}
            </div>
          );
        })}
      </nav>
      <button
        type="button"
        className="app-nav-collapse-btn"
        ref={desktopToggle}
        onClick={() => setCollapsed((value) => !value)}
        aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
        aria-expanded={!collapsed}
        aria-controls="app-primary-links"
        title={collapsed ? "展开侧栏" : "收起侧栏"}
      >
        <MaterialIcon name={collapsed ? "chevron_right" : "chevron_left"} size={18} />
        <span className="app-nav-label">收起</span>
      </button>
    </aside>
  );
}
