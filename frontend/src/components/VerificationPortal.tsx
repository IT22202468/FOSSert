import React, { useEffect, useState } from "react";
import BlockRoundedIcon from "@mui/icons-material/BlockRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import DownloadRoundedIcon from "@mui/icons-material/DownloadRounded";
import { api } from "../api";
import type { CertificateVerificationResult } from "../types";

export const VerificationPortal: React.FC = () => {
  const [code, setCode] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<CertificateVerificationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Check URL query param on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const codeParam = params.get("code");
    if (codeParam) {
      setCode(codeParam);
      performVerify(codeParam);
    }
  }, []);

  const performVerify = async (codeToVerify: string) => {
    const clean = codeToVerify.trim();
    if (!clean) {
      setError("Please enter a Certificate ID");
      setResult(null);
      return;
    }

    setError(null);
    setIsLoading(true);
    setResult(null);

    // Update URL query param without full reload
    const url = new URL(window.location.href);
    url.searchParams.set("code", clean);
    window.history.replaceState({}, "", url.toString());

    try {
      const data = await api.verifyCertificate(clean);
      setResult(data);
    } catch (err: any) {
      if (err?.status === 404) {
        setError(`No official certificate was found matching ID "${clean}". Please double-check the ID printed on the certificate.`);
      } else {
        setError(err?.message || "An error occurred while verifying the certificate.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    performVerify(code);
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{ maxWidth: "880px", margin: "0 auto", padding: "1.5rem 1rem" }}>
      {/* Verification Header */}
      <div style={{ textAlign: "center", marginBottom: "2.5rem" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: "16px", marginBottom: "1.25rem" }}>
          <img
            src="/branding/FOSSert Certificate Verification Logo.png"
            alt="FOSSert Certificate Verification"
            style={{ height: "46px", maxWidth: "220px", objectFit: "contain" }}
          />
          <span style={{ color: "#d4d4d8", fontSize: "1.5rem" }}>|</span>
          <img
            src="/branding/FOSS-logo.png"
            alt="SLIIT FOSS Community"
            style={{ height: "38px", maxWidth: "120px", objectFit: "contain" }}
          />
        </div>
        <h1 style={{ fontSize: "2rem", fontWeight: 800, color: "#111111", margin: "0 0 0.5rem", letterSpacing: "-0.02em" }}>
          Official Certificate Verification
        </h1>
        <p style={{ fontSize: "1rem", color: "#777777", maxWidth: "600px", margin: "0 auto", lineHeight: "24px" }}>
          Verify the authenticity of digital certificates issued by the SLIIT Free and Open Source Software (FOSS) Community.
        </p>
      </div>

      {/* Search Input Box */}
      <div
        style={{
          backgroundColor: "#ffffff",
          border: "1px solid rgba(0, 0, 0, 0.06)",
          borderRadius: "21.6px",
          padding: "1.5rem",
          boxShadow: "0 4px 20px rgba(0, 0, 0, 0.04)",
          marginBottom: "2rem",
        }}
      >
        <form onSubmit={handleSubmit} style={{ display: "flex", gap: "12px", flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ flex: "1 1 300px", position: "relative" }}>
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="e.g. FOSS-2026-XXXX-XXXX"
              style={{
                width: "100%",
                padding: "0.85rem 1.4rem",
                borderRadius: "9999px",
                backgroundColor: "#ffffff",
                border: "1.5px solid #eeeeee",
                color: "#111111",
                fontSize: "1rem",
                fontFamily: "monospace",
                boxSizing: "border-box",
                outline: "none",
                letterSpacing: "0.05em",
                transition: "border-color 200ms ease, box-shadow 200ms ease",
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
            {code && (
              <button
                type="button"
                onClick={() => setCode("")}
                style={{
                  position: "absolute",
                  right: "16px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  color: "#a1a1aa",
                  cursor: "pointer",
                  fontSize: "1rem",
                }}
                aria-label="Clear code"
              >
                <CloseRoundedIcon sx={{ fontSize: 18 }} />
              </button>
            )}
          </div>
          <button
            type="submit"
            disabled={isLoading || !code.trim()}
            style={{
              padding: "0.85rem 2rem",
              borderRadius: "9999px",
              border: "none",
              backgroundColor: isLoading || !code.trim() ? "#f4f4f5" : "#dc2626",
              color: isLoading || !code.trim() ? "#a1a1aa" : "#ffffff",
              fontSize: "0.95rem",
              fontWeight: 600,
              cursor: isLoading || !code.trim() ? "not-allowed" : "pointer",
              boxShadow: isLoading || !code.trim() ? "none" : "0 4px 14px rgba(220, 38, 38, 0.25)",
              transition: "all 200ms ease",
            }}
          >
            {isLoading ? "Verifying..." : "Verify Certificate"}
          </button>
        </form>
        <p style={{ margin: "0.75rem 0 0", fontSize: "0.8rem", color: "#777777", paddingLeft: "4px" }}>
          Tip: Enter the Certificate ID printed along the bottom edge of your official certificate.
        </p>
      </div>

      {/* Error / Not Found Alert */}
      {error && (
        <div
          style={{
            padding: "1.25rem 1.5rem",
            backgroundColor: "#fef2f2",
            border: "1px solid #fecaca",
            borderRadius: "21.6px",
            color: "#b91c1c",
            marginBottom: "2rem",
            display: "flex",
            alignItems: "flex-start",
            gap: "12px",
          }}
        >
          <WarningAmberRoundedIcon sx={{ fontSize: 26, color: "#dc2626", flexShrink: 0, mt: 0.2 }} />
          <div>
            <h3 style={{ margin: "0 0 0.25rem", fontSize: "1rem", fontWeight: 700, color: "#991b1b" }}>
              Certificate Not Verified
            </h3>
            <p style={{ margin: 0, fontSize: "0.9rem", color: "#b91c1c", lineHeight: "20px" }}>{error}</p>
          </div>
        </div>
      )}

      {/* Verified / Revoked Certificate Card */}
      {result && result.found && (
        <div
          style={{
            backgroundColor: "#ffffff",
            border: result.is_revoked
              ? "1.5px solid rgba(220, 38, 38, 0.35)"
              : "1px solid rgba(22, 163, 74, 0.25)",
            borderRadius: "21.6px",
            padding: "2rem",
            boxShadow: result.is_revoked
              ? "0 8px 30px rgba(220, 38, 38, 0.08), 0 2px 8px rgba(0, 0, 0, 0.03)"
              : "0 8px 30px rgba(22, 163, 74, 0.08), 0 2px 8px rgba(0, 0, 0, 0.03)",
            marginBottom: "2rem",
            position: "relative",
            overflow: "hidden",
          }}
        >
          {/* Top Verification Badge */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "1rem",
              paddingBottom: "1.5rem",
              borderBottom: "1px solid rgba(0, 0, 0, 0.06)",
              marginBottom: "1.5rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <div
                style={{
                  width: "38px",
                  height: "38px",
                  borderRadius: "50%",
                  backgroundColor: result.is_revoked ? "#fef2f2" : "#f0fdf4",
                  border: result.is_revoked ? "2px solid #dc2626" : "2px solid #16a34a",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: result.is_revoked ? "#dc2626" : "#16a34a",
                }}
              >
                {result.is_revoked ? (
                  <BlockRoundedIcon sx={{ fontSize: 22, color: "#dc2626" }} />
                ) : (
                  <CheckRoundedIcon sx={{ fontSize: 22, color: "#16a34a" }} />
                )}
              </div>
              <div>
                <span
                  style={{
                    fontSize: "0.75rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                    color: result.is_revoked ? "#dc2626" : "#16a34a",
                    fontWeight: 800,
                  }}
                >
                  {result.is_revoked
                    ? "Official Record: Revoked & Invalidated"
                    : "Official Record Verified"}
                </span>
                <h2 style={{ fontSize: "1.25rem", margin: 0, color: result.is_revoked ? "#991b1b" : "#111111", fontWeight: 700 }}>
                  {result.is_revoked
                    ? "Certificate Invalidated by Authority"
                    : "Authentic Certificate of Participation"}
                </h2>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span
                style={{
                  fontFamily: "monospace",
                  backgroundColor: "#f4f4f5",
                  border: "1px solid #eeeeee",
                  padding: "0.4rem 0.9rem",
                  borderRadius: "9999px",
                  fontSize: "0.85rem",
                  color: "#111111",
                  fontWeight: 600,
                }}
              >
                {result.certificate_code}
              </span>
              <button
                type="button"
                onClick={() => copyToClipboard(result.certificate_code)}
                style={{
                  padding: "0.4rem 0.9rem",
                  borderRadius: "9999px",
                  border: "1px solid #eeeeee",
                  backgroundColor: "#ffffff",
                  color: "#111111",
                  fontSize: "0.8rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "background-color 150ms ease",
                }}
                onMouseOver={(e) => (e.currentTarget.style.backgroundColor = "#f4f4f5")}
                onMouseOut={(e) => (e.currentTarget.style.backgroundColor = "#ffffff")}
              >
                {copied ? "Copied!" : "Copy ID"}
              </button>
            </div>
          </div>

          {/* Revocation Warning Alert if Revoked */}
          {result.is_revoked && (
            <div
              style={{
                padding: "1.1rem 1.4rem",
                backgroundColor: "#fef2f2",
                border: "1px solid #fee2e2",
                borderRadius: "16px",
                marginBottom: "1.75rem",
                color: "#991b1b",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 700, fontSize: "1rem", marginBottom: "0.35rem" }}>
                <BlockRoundedIcon sx={{ fontSize: 20, color: "#dc2626" }} />
                <span>Notice of Certificate Invalidation</span>
              </div>
              <p style={{ margin: "0 0 0.5rem", fontSize: "0.925rem", color: "#b91c1c", lineHeight: 1.5 }}>
                This certificate was officially invalidated by the SLIIT FOSS Community authority and is no longer recognized as an authentic credential.
              </p>
              {result.revocation_reason && (
                <div style={{ fontSize: "0.9rem", color: "#7f1d1d", marginBottom: "0.25rem" }}>
                  <strong>Revocation Reason:</strong> {result.revocation_reason}
                </div>
              )}
              {result.revoked_at && (
                <div style={{ fontSize: "0.825rem", color: "#991b1b" }}>
                  <strong>Invalidated on:</strong>{" "}
                  {new Date(result.revoked_at).toLocaleDateString(undefined, {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                  })}
                </div>
              )}
            </div>
          )}

          {/* Details Grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: "1.5rem",
              marginBottom: "2rem",
            }}
          >
            <div>
              <span style={{ fontSize: "0.75rem", color: "#777777", textTransform: "uppercase", fontWeight: 600 }}>
                Recipient Name
              </span>
              <p style={{ margin: "0.25rem 0 0", fontSize: "1.5rem", fontWeight: 800, color: "#111111" }}>
                {result.recipient_name}
              </p>
            </div>

            <div>
              <span style={{ fontSize: "0.75rem", color: "#777777", textTransform: "uppercase", fontWeight: 600 }}>
                Event / Workshop
              </span>
              <p style={{ margin: "0.25rem 0 0", fontSize: "1.1rem", fontWeight: 600, color: "#111111" }}>
                {result.workshop_name}
              </p>
            </div>

            <div>
              <span style={{ fontSize: "0.75rem", color: "#777777", textTransform: "uppercase", fontWeight: 600 }}>
                Issuing Organization
              </span>
              <p style={{ margin: "0.25rem 0 0", fontSize: "1.1rem", fontWeight: 600, color: "#dc2626" }}>
                {result.issuer}
              </p>
            </div>

            <div>
              <span style={{ fontSize: "0.75rem", color: "#777777", textTransform: "uppercase", fontWeight: 600 }}>
                Date of Issuance
              </span>
              <p style={{ margin: "0.25rem 0 0", fontSize: "1.1rem", fontWeight: 500, color: "#333333" }}>
                {result.issue_date ? new Date(result.issue_date).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" }) : "Certified Record"}
              </p>
            </div>
          </div>

          {/* Certificate Image Preview */}
          {result.has_preview && (
            <div style={{ marginBottom: "2rem" }}>
              <span style={{ display: "block", fontSize: "0.85rem", color: "#777777", marginBottom: "0.75rem", fontWeight: 600 }}>
                Official Certificate Preview:
              </span>
              <div
                style={{
                  borderRadius: "16px",
                  overflow: "hidden",
                  border: "1px solid #eeeeee",
                  boxShadow: "0 4px 20px rgba(0, 0, 0, 0.05)",
                  backgroundColor: "#f4f4f5",
                  textAlign: "center",
                }}
              >
                <img
                  src={`/api/verify/${encodeURIComponent(result.certificate_code)}/preview`}
                  alt={`Certificate for ${result.recipient_name}`}
                  style={{ width: "100%", maxHeight: "550px", objectFit: "contain", display: "block" }}
                />
              </div>
            </div>
          )}

          {/* Action Bar / Download */}
          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", justifyContent: result.is_revoked ? "space-between" : "flex-end", alignItems: "center" }}>
            {result.is_revoked ? (
              <>
                <span style={{ fontSize: "0.85rem", color: "#991b1b", fontWeight: 600 }}>
                  Direct PDF downloads are permanently disabled for invalidated credentials.
                </span>
                <button
                  type="button"
                  disabled
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "8px",
                    padding: "0.8rem 1.8rem",
                    borderRadius: "9999px",
                    backgroundColor: "#f4f4f5",
                    color: "#a1a1aa",
                    border: "1px solid #e4e4e7",
                    cursor: "not-allowed",
                    fontWeight: 600,
                    fontSize: "0.95rem",
                  }}
                >
                  <BlockRoundedIcon sx={{ fontSize: 18 }} />
                  <span>Download Disabled (Revoked)</span>
                </button>
              </>
            ) : (
              result.has_pdf && (
                <a
                  href={`/api/verify/${encodeURIComponent(result.certificate_code)}/download`}
                  download
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "8px",
                    padding: "0.8rem 1.8rem",
                    borderRadius: "9999px",
                    backgroundColor: "#dc2626",
                    color: "#ffffff",
                    textDecoration: "none",
                    fontWeight: 600,
                    fontSize: "0.95rem",
                    boxShadow: "0 4px 14px rgba(220, 38, 38, 0.25)",
                    transition: "all 150ms ease",
                  }}
                >
                  <DownloadRoundedIcon sx={{ fontSize: 19 }} />
                  <span>Download Official PDF</span>
                </a>
              )
            )}
          </div>
        </div>
      )}

      {/* Information / Explainer Section */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: "1.25rem",
          marginTop: "3rem",
        }}
      >
        <div style={{ backgroundColor: "#ffffff", border: "1px solid rgba(0, 0, 0, 0.06)", borderRadius: "21.6px", padding: "1.5rem" }}>
          <h4 style={{ color: "#111111", margin: "0 0 0.5rem", fontSize: "0.95rem", fontWeight: 700 }}>
            About FOSSert Verification
          </h4>
          <p style={{ margin: 0, lineHeight: 1.6, color: "#777777", fontSize: "0.875rem" }}>
            Every certificate issued by the SLIIT FOSS Community receives a cryptographically unique identifier and is logged in our permanent record store.
          </p>
        </div>
        <div style={{ backgroundColor: "#ffffff", border: "1px solid rgba(0, 0, 0, 0.06)", borderRadius: "21.6px", padding: "1.5rem" }}>
          <h4 style={{ color: "#111111", margin: "0 0 0.5rem", fontSize: "0.95rem", fontWeight: 700 }}>
            Locating your Certificate ID
          </h4>
          <p style={{ margin: 0, lineHeight: 1.6, color: "#777777", fontSize: "0.875rem" }}>
            Look along the bottom center edge of your certificate PDF or printout for <code>Certificate ID: FOSS-2026-XXXX-XXXX</code>.
          </p>
        </div>
        <div style={{ backgroundColor: "#ffffff", border: "1px solid rgba(0, 0, 0, 0.06)", borderRadius: "21.6px", padding: "1.5rem" }}>
          <h4 style={{ color: "#111111", margin: "0 0 0.5rem", fontSize: "0.95rem", fontWeight: 700 }}>
            Need Assistance?
          </h4>
          <p style={{ margin: 0, lineHeight: 1.6, color: "#777777", fontSize: "0.875rem" }}>
            For verification inquiries or record amendments, reach out to the SLIIT FOSS Community leadership team.
          </p>
        </div>
      </div>
    </div>
  );
};
