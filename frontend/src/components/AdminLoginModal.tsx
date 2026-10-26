import React, { useState } from "react";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import { api } from "../api";

interface AdminLoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (username: string) => void;
}

export const AdminLoginModal: React.FC<AdminLoginModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError("Please provide both username and password");
      return;
    }
    setError(null);
    setIsLoading(true);
    try {
      const res = await api.login(username.trim(), password);
      onSuccess(res.username);
      setPassword("");
    } catch (err: any) {
      setError(err?.message || "Invalid credentials. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.45)",
        backdropFilter: "blur(6px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
        padding: "1rem",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "420px",
          backgroundColor: "#ffffff",
          border: "1px solid rgba(0, 0, 0, 0.08)",
          borderRadius: "21.6px",
          padding: "2rem",
          boxShadow: "0 20px 50px rgba(0, 0, 0, 0.12)",
          color: "#111111",
          position: "relative",
        }}
      >
        <button
          type="button"
          onClick={onClose}
          style={{
            position: "absolute",
            top: "18px",
            right: "18px",
            background: "none",
            border: "none",
            color: "#a1a1aa",
            fontSize: "1.25rem",
            cursor: "pointer",
            lineHeight: 1,
            padding: "4px 8px",
            borderRadius: "50%",
          }}
          aria-label="Close modal"
        >
          <CloseRoundedIcon sx={{ fontSize: 20 }} />
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "1rem" }}>
          <img
            src="/branding/FOSSert Certificate Verification Logo.png"
            alt="FOSSert"
            style={{ height: "36px", maxWidth: "80px", objectFit: "contain" }}
          />
          <div>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "#111111" }}>
              Admin Sign In
            </h2>
            <p style={{ margin: 0, fontSize: "0.8rem", color: "#777777" }}>
              SLIIT FOSS Community Superuser
            </p>
          </div>
        </div>

        <p style={{ fontSize: "0.875rem", color: "#777777", marginBottom: "1.5rem", lineHeight: 1.5 }}>
          Enter superuser credentials to manage sessions, templates, generated certificates, and email dispatches.
        </p>

        {error && (
          <div
            style={{
              padding: "0.75rem 1rem",
              backgroundColor: "#fef2f2",
              border: "1px solid #fecaca",
              borderRadius: "12px",
              color: "#b91c1c",
              fontSize: "0.85rem",
              marginBottom: "1.25rem",
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: "1rem" }}>
            <label
              htmlFor="admin-username"
              style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "#333333", marginBottom: "0.4rem" }}
            >
              Username
            </label>
            <input
              id="admin-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              required
              autoFocus
              style={{
                width: "100%",
                padding: "0.75rem 1rem",
                borderRadius: "12px",
                backgroundColor: "#ffffff",
                border: "1.5px solid #eeeeee",
                color: "#111111",
                fontSize: "0.95rem",
                boxSizing: "border-box",
                outline: "none",
                transition: "border-color 150ms ease, box-shadow 150ms ease",
              }}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = "#dc2626";
                e.currentTarget.style.boxShadow = "0 0 0 3px rgba(220, 38, 38, 0.2)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = "#eeeeee";
                e.currentTarget.style.boxShadow = "none";
              }}
            />
          </div>

          <div style={{ marginBottom: "1.5rem" }}>
            <label
              htmlFor="admin-password"
              style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "#333333", marginBottom: "0.4rem" }}
            >
              Password
            </label>
            <input
              id="admin-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter superuser password"
              required
              style={{
                width: "100%",
                padding: "0.75rem 1rem",
                borderRadius: "12px",
                backgroundColor: "#ffffff",
                border: "1.5px solid #eeeeee",
                color: "#111111",
                fontSize: "0.95rem",
                boxSizing: "border-box",
                outline: "none",
                transition: "border-color 150ms ease, box-shadow 150ms ease",
              }}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = "#dc2626";
                e.currentTarget.style.boxShadow = "0 0 0 3px rgba(220, 38, 38, 0.2)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = "#eeeeee";
                e.currentTarget.style.boxShadow = "none";
              }}
            />
          </div>

          <div style={{ display: "flex", gap: "10px", justifyContent: "flex-end" }}>
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              style={{
                padding: "0.65rem 1.4rem",
                borderRadius: "9999px",
                border: "1px solid #eeeeee",
                backgroundColor: "#ffffff",
                color: "#333333",
                fontSize: "0.9rem",
                fontWeight: 600,
                cursor: "pointer",
                transition: "background-color 150ms ease",
              }}
              onMouseOver={(e) => (e.currentTarget.style.backgroundColor = "#f4f4f5")}
              onMouseOut={(e) => (e.currentTarget.style.backgroundColor = "#ffffff")}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              style={{
                padding: "0.65rem 1.6rem",
                borderRadius: "9999px",
                border: "none",
                backgroundColor: "#dc2626",
                color: "#ffffff",
                fontSize: "0.9rem",
                fontWeight: 600,
                cursor: isLoading ? "not-allowed" : "pointer",
                boxShadow: "0 4px 12px rgba(220, 38, 38, 0.25)",
                transition: "background-color 150ms ease",
              }}
              onMouseOver={(e) => !isLoading && (e.currentTarget.style.backgroundColor = "#b91c1c")}
              onMouseOut={(e) => !isLoading && (e.currentTarget.style.backgroundColor = "#dc2626")}
            >
              {isLoading ? "Signing in..." : "Sign In"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
