import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useToast } from "../../hooks/useToast";

describe("useToast", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts with empty toasts", () => {
    const { result } = renderHook(() => useToast());
    expect(result.current.toasts).toEqual([]);
  });

  it("addToast adds a toast", () => {
    const { result } = renderHook(() => useToast());
    act(() => {
      result.current.addToast("success", "Done!");
    });
    expect(result.current.toasts).toHaveLength(1);
    expect(result.current.toasts[0].type).toBe("success");
    expect(result.current.toasts[0].message).toBe("Done!");
  });

  it("dismiss removes a toast by id", () => {
    const { result } = renderHook(() => useToast());
    let id: number;
    act(() => {
      id = result.current.addToast("error", "Oops");
    });
    expect(result.current.toasts).toHaveLength(1);
    act(() => {
      result.current.dismiss(id);
    });
    expect(result.current.toasts).toHaveLength(0);
  });

  it("auto-dismisses after timeout", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useToast(1000));
    act(() => {
      result.current.addToast("info", "Temporary");
    });
    expect(result.current.toasts).toHaveLength(1);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.toasts).toHaveLength(0);
    vi.useRealTimers();
  });

  it("can stack multiple toasts", () => {
    const { result } = renderHook(() => useToast());
    act(() => {
      result.current.addToast("success", "First");
      result.current.addToast("warning", "Second");
    });
    expect(result.current.toasts).toHaveLength(2);
  });
});
