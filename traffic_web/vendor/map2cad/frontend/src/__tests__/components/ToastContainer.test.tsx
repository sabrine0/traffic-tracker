import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ToastContainer from "../../components/ui/Toast";
import type { Toast } from "../../hooks/useToast";

const mockToasts: Toast[] = [
  { id: 1, type: "success", message: "Export complete" },
  { id: 2, type: "error", message: "Something failed" },
];

describe("ToastContainer", () => {
  it("renders nothing when toasts array is empty", () => {
    const { container } = render(<ToastContainer toasts={[]} onDismiss={() => {}} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders toast messages", () => {
    render(<ToastContainer toasts={mockToasts} onDismiss={() => {}} />);
    expect(screen.getByText("Export complete")).toBeInTheDocument();
    expect(screen.getByText("Something failed")).toBeInTheDocument();
  });

  it("renders toasts with alert role", () => {
    render(<ToastContainer toasts={mockToasts} onDismiss={() => {}} />);
    expect(screen.getAllByRole("alert")).toHaveLength(2);
  });

  it("calls onDismiss when toast clicked", async () => {
    const user = userEvent.setup();
    const dismiss = vi.fn();
    render(<ToastContainer toasts={mockToasts} onDismiss={dismiss} />);
    await user.click(screen.getByText("Export complete"));
    expect(dismiss).toHaveBeenCalledWith(1);
  });

  it("has aria-live polite container", () => {
    render(<ToastContainer toasts={mockToasts} onDismiss={() => {}} />);
    const container = screen.getByText("Export complete").closest("[aria-live]");
    expect(container).toHaveAttribute("aria-live", "polite");
  });
});
