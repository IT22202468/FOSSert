import { Box } from "@mui/material";

type BrandMarkProps = {
  variant?: "icon" | "horizontal" | "foss";
  size?: number;
  width?: number | string;
  priority?: boolean;
};

export default function BrandMark({
  variant = "icon",
  size = 44,
  width,
  priority = false,
}: BrandMarkProps) {
  const horizontal = variant === "horizontal";
  const foss = variant === "foss";
  const src = foss
    ? "/branding/FOSS-logo.png"
    : "/branding/FOSSert Certificate Verification Logo.png";
  const alt = foss ? "SLIIT FOSS Community" : "FOSSert";

  return (
    <Box
      component="img"
      src={src}
      alt={alt}
      loading={priority ? "eager" : "lazy"}
      fetchPriority={priority ? "high" : "auto"}
      draggable={false}
      sx={{
        display: "block",
        width: width ?? "auto",
        height: size,
        maxWidth: "100%",
        objectFit: "contain",
        objectPosition: "left center",
        flex: "0 0 auto",
        userSelect: "none",
      }}
    />
  );
}
