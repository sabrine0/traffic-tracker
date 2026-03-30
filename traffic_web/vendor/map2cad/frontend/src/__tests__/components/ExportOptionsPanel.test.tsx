import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ExportOptionsPanel from "../../components/ExportOptions";
import { ExportProvider } from "../../context/ExportContext";

function renderWithProvider() {
  return render(
    <ExportProvider>
      <ExportOptionsPanel />
    </ExportProvider>
  );
}

describe("ExportOptionsPanel", () => {
  it("renders all 13 toggle options", () => {
    renderWithProvider();
    // Road layers
    expect(screen.getByText("Lane Markings")).toBeInTheDocument();
    expect(screen.getByText("Sidewalks")).toBeInTheDocument();
    expect(screen.getByText("Curbs")).toBeInTheDocument();
    expect(screen.getByText("Intersections")).toBeInTheDocument();
    expect(screen.getByText("Road Names")).toBeInTheDocument();
    // Feature layers
    expect(screen.getByText("Buildings")).toBeInTheDocument();
    expect(screen.getByText("Land Use")).toBeInTheDocument();
    expect(screen.getByText("Railways")).toBeInTheDocument();
    expect(screen.getByText("Parking")).toBeInTheDocument();
    expect(screen.getByText("Traffic Signals")).toBeInTheDocument();
    expect(screen.getByText("Street Furniture")).toBeInTheDocument();
    expect(screen.getByText("Cycling")).toBeInTheDocument();
    expect(screen.getByText("Utilities")).toBeInTheDocument();
  });

  it("road layers checked and feature layers unchecked by default", () => {
    renderWithProvider();
    const switches = screen.getAllByRole("switch");
    expect(switches).toHaveLength(13);
    // First 5 (road layers) are ON by default
    for (let i = 0; i < 5; i++) {
      expect(switches[i]).toHaveAttribute("aria-checked", "true");
    }
    // Last 8 (feature layers) are OFF by default
    for (let i = 5; i < 13; i++) {
      expect(switches[i]).toHaveAttribute("aria-checked", "false");
    }
  });

  it("toggles a switch off when clicked", async () => {
    const user = userEvent.setup();
    renderWithProvider();
    const laneSwitch = screen.getByLabelText("Toggle Lane Markings");
    expect(laneSwitch).toHaveAttribute("aria-checked", "true");
    await user.click(laneSwitch);
    expect(laneSwitch).toHaveAttribute("aria-checked", "false");
  });

  it("toggles a switch back on when clicked twice", async () => {
    const user = userEvent.setup();
    renderWithProvider();
    const sw = screen.getByLabelText("Toggle Sidewalks");
    await user.click(sw);
    expect(sw).toHaveAttribute("aria-checked", "false");
    await user.click(sw);
    expect(sw).toHaveAttribute("aria-checked", "true");
  });
});
