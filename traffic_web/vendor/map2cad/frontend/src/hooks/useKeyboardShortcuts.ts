import { useEffect } from "react";

interface ShortcutActions {
  onEscape?: () => void;
  onExport?: () => void;
  onFocusSearch?: () => void;
}

function isTyping(): boolean {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || (el as HTMLElement).isContentEditable;
}

export function useKeyboardShortcuts({ onEscape, onExport, onFocusSearch }: ShortcutActions) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Escape always works
      if (e.key === "Escape") {
        onEscape?.();
        (document.activeElement as HTMLElement)?.blur();
        return;
      }

      // Skip other shortcuts while typing
      if (isTyping()) return;

      if (e.key === "Enter" && !e.metaKey && !e.ctrlKey) {
        onExport?.();
        return;
      }

      if (e.key === "/") {
        e.preventDefault();
        onFocusSearch?.();
        return;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onEscape, onExport, onFocusSearch]);
}
