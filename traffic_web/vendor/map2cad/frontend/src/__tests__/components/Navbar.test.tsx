import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Navbar from "../../components/Navbar";

describe("Navbar", () => {
  it("renders brand name", () => {
    render(<Navbar onToggleSidebar={() => {}} sidebarOpen={false} />);
    expect(screen.getByText("Map2CAD")).toBeInTheDocument();
  });

  it("has main navigation aria-label", () => {
    render(<Navbar onToggleSidebar={() => {}} sidebarOpen={false} />);
    expect(screen.getByRole("navigation", { name: /main navigation/i })).toBeInTheDocument();
  });

  it("renders a dashboard return link", () => {
    render(<Navbar onToggleSidebar={() => {}} sidebarOpen={false} />);
    expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute("href", "/admin");
  });

  it("calls onToggleSidebar when hamburger clicked", async () => {
    const user = userEvent.setup();
    const toggle = vi.fn();
    render(<Navbar onToggleSidebar={toggle} sidebarOpen={false} />);
    await user.click(screen.getByLabelText("Toggle sidebar"));
    expect(toggle).toHaveBeenCalledOnce();
  });
});
