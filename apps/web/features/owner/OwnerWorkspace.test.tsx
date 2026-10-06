import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { requestMock, logoutMock } = vi.hoisted(() => ({
  requestMock: vi.fn(async () => []),
  logoutMock: vi.fn(async () => undefined),
}));

vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({
    session: { access_token: "owner-token" },
    request: requestMock,
    logout: logoutMock,
  }),
}));

import { OwnerWorkspace } from "./OwnerWorkspace";

function layoutFor(navigation: HTMLElement) {
  const layout = navigation.parentElement;
  if (!layout) throw new Error("Owner layout was not rendered");
  return layout;
}

beforeEach(() => {
  requestMock.mockClear();
  logoutMock.mockClear();
  window.localStorage.clear();
  window.scrollTo = vi.fn();
  window.requestAnimationFrame = (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  };
  window.cancelAnimationFrame = vi.fn();
});

afterEach(cleanup);

describe("Owner sidebar", () => {
  it("starts collapsed, expands on hover, and collapses on mouse leave", async () => {
    render(<OwnerWorkspace />);
    await screen.findByRole("heading", { name: "Operations overview" });
    const navigation = screen.getByRole("navigation", { name: "Owner sections" });
    const layout = layoutFor(navigation);

    expect(layout).toHaveAttribute("data-sidebar-expanded", "false");
    fireEvent.mouseEnter(navigation);
    expect(layout).toHaveAttribute("data-sidebar-expanded", "true");
    fireEvent.mouseLeave(navigation);
    expect(layout).toHaveAttribute("data-sidebar-expanded", "false");
  });

  it("collapses temporary expansion after navigation and keeps the route highlighted", async () => {
    render(<OwnerWorkspace />);
    await screen.findByRole("heading", { name: "Operations overview" });
    const navigation = screen.getByRole("navigation", { name: "Owner sections" });
    const layout = layoutFor(navigation);
    const deployments = screen.getByRole("button", { name: "Deployments" });

    fireEvent.mouseEnter(navigation);
    fireEvent.mouseDown(deployments);
    fireEvent.focus(deployments);
    fireEvent.click(deployments);
    fireEvent.mouseLeave(navigation);

    expect(await screen.findByRole("heading", { name: "Deployments" })).toBeInTheDocument();
    expect(layout).toHaveAttribute("data-sidebar-expanded", "false");
    expect(deployments).toHaveAttribute("aria-current", "page");
  });

  it("keeps a pinned sidebar expanded across navigation and unpin restores hover behavior", async () => {
    render(<OwnerWorkspace />);
    await screen.findByRole("heading", { name: "Operations overview" });
    const navigation = screen.getByRole("navigation", { name: "Owner sections" });
    const layout = layoutFor(navigation);

    fireEvent.click(screen.getByRole("button", { name: "Pin sidebar" }));
    expect(layout).toHaveAttribute("data-sidebar-pinned", "true");
    fireEvent.click(screen.getByRole("button", { name: "Assignments" }));
    fireEvent.mouseLeave(navigation);
    expect(await screen.findByRole("heading", { name: "Assignments" })).toBeInTheDocument();
    expect(layout).toHaveAttribute("data-sidebar-expanded", "true");

    fireEvent.click(screen.getByRole("button", { name: "Unpin sidebar" }));
    expect(layout).toHaveAttribute("data-sidebar-pinned", "false");
    expect(layout).toHaveAttribute("data-sidebar-expanded", "false");
  });

  it("expands for keyboard focus and releases expansion when focus leaves", async () => {
    render(<OwnerWorkspace />);
    await screen.findByRole("heading", { name: "Operations overview" });
    const navigation = screen.getByRole("navigation", { name: "Owner sections" });
    const layout = layoutFor(navigation);
    const assignments = screen.getByRole("button", { name: "Assignments" });

    fireEvent.focus(assignments);
    expect(layout).toHaveAttribute("data-sidebar-expanded", "true");
    fireEvent.blur(assignments, { relatedTarget: null });
    await waitFor(() => expect(layout).toHaveAttribute("data-sidebar-expanded", "false"));
  });
});
