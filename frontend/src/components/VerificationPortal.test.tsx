import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { VerificationPortal } from "./VerificationPortal";
import { AdminLoginModal } from "./AdminLoginModal";
import { api } from "../api";

describe("VerificationPortal", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState({}, "", "/");
  });

  afterEach(() => {
    cleanup();
    window.history.replaceState({}, "", "/");
  });

  it("renders search input, tips, and verify button", () => {
    render(<VerificationPortal />);
    expect(screen.getByPlaceholderText(/e\.g\. FOSS-2026/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /verify certificate/i })).toBeInTheDocument();
  });

  it("displays verified certificate details on successful verification", async () => {
    vi.spyOn(api, "verifyCertificate").mockResolvedValue({
      found: true,
      certificate_code: "FOSS-2026-TEST-CODE",
      recipient_name: "Test Recipient",
      workshop_name: "React & Cloud Workshop",
      issuer: "SLIIT FOSS Community",
      issue_date: "2026-10-26T10:00:00Z",
      status: "ISSUED",
      verified: true,
      has_pdf: true,
      has_preview: true,
    });

    render(<VerificationPortal />);
    const input = screen.getByPlaceholderText(/e\.g\. FOSS-2026/i);
    fireEvent.change(input, { target: { value: "FOSS-2026-TEST-CODE" } });

    const btn = screen.getByRole("button", { name: /verify certificate/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByText("Test Recipient")).toBeInTheDocument();
      expect(screen.getByText("React & Cloud Workshop")).toBeInTheDocument();
      expect(screen.getByText("Official Record Verified")).toBeInTheDocument();
      expect(screen.getByText("Download Official PDF")).toBeInTheDocument();
    });
  });

  it("shows not verified alert when code does not exist", async () => {
    vi.spyOn(api, "verifyCertificate").mockRejectedValue({
      status: 404,
      message: "Certificate not found",
    });

    render(<VerificationPortal />);
    const input = screen.getByPlaceholderText(/e\.g\. FOSS-2026/i);
    fireEvent.change(input, { target: { value: "INVALID-CODE" } });

    const btn = screen.getByRole("button", { name: /verify certificate/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByText(/Certificate Not Verified/i)).toBeInTheDocument();
      expect(screen.getByText(/No official certificate was found matching ID "INVALID-CODE"/i)).toBeInTheDocument();
    });
  });

  it("displays revoked alert and disables download when certificate is revoked", async () => {
    vi.spyOn(api, "verifyCertificate").mockResolvedValue({
      found: true,
      certificate_code: "FOSS-2026-REVOKED-1",
      recipient_name: "Wrong Recipient",
      workshop_name: "React & Cloud Workshop",
      issuer: "SLIIT FOSS Community",
      issue_date: "2026-10-26T10:00:00Z",
      status: "REVOKED",
      verified: false,
      is_revoked: true,
      revoked_at: "2026-10-26T12:00:00Z",
      revocation_reason: "Issued to wrong recipient by mistake",
      has_pdf: false,
      has_preview: false,
    });

    render(<VerificationPortal />);
    const input = screen.getByPlaceholderText(/e\.g\. FOSS-2026/i);
    fireEvent.change(input, { target: { value: "FOSS-2026-REVOKED-1" } });

    const btn = screen.getByRole("button", { name: /verify certificate/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByText("Wrong Recipient")).toBeInTheDocument();
      expect(screen.getByText(/Certificate Invalidated by Authority/i)).toBeInTheDocument();
      expect(screen.getByText(/Notice of Certificate Invalidation/i)).toBeInTheDocument();
      expect(screen.getByText(/Issued to wrong recipient by mistake/i)).toBeInTheDocument();
      expect(screen.getByText(/Download Disabled \(Revoked\)/i)).toBeInTheDocument();
    });
  });
});

describe("AdminLoginModal", () => {
  it("submits superuser credentials and calls onSuccess", async () => {
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    vi.spyOn(api, "login").mockResolvedValue({ token: "test-token-123", username: "admin" });

    render(
      <AdminLoginModal
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    const usernameInput = screen.getByPlaceholderText(/Enter username/i);
    fireEvent.change(usernameInput, { target: { value: "admin" } });
    const passwordInput = screen.getByPlaceholderText(/Enter superuser password/i);
    fireEvent.change(passwordInput, { target: { value: "sliitfossadmin" } });

    const submitBtn = screen.getByRole("button", { name: /^sign in$/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.login).toHaveBeenCalledWith("admin", "sliitfossadmin");
      expect(onSuccess).toHaveBeenCalledWith("admin");
    });
  });
});
