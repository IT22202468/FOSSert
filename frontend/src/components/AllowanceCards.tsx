import { Alert, Box, Paper, Typography } from "@mui/material";
import type { Allowance } from "../types";

const items: [
  keyof Pick<Allowance, "used" | "successful" | "failed" | "uncertain">,
  string,
  string,
][] = [
  ["used", "Counted activity (24h)", "#dc2626"],
  ["successful", "Successful sends", "#16a34a"],
  ["failed", "Failed attempts", "#dc2626"],
  ["uncertain", "Uncertain attempts", "#d97706"],
];

export default function AllowanceCards({
  allowance,
}: {
  allowance: Allowance;
}) {
  return (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 1, color: "#111111", fontWeight: 700 }}>
        Sending activity · rolling 24 hours
      </Typography>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))",
          gap: 1.5,
          mb: 1.5,
        }}
      >
        {allowance.enabled && (
          <Paper variant="outlined" sx={{ p: 2, bgcolor: "#ffffff", border: "1px solid rgba(0, 0, 0, 0.06)", borderRadius: "21.6px" }}>
            <Typography variant="caption" color="text.secondary">
              Configured app cap remaining
            </Typography>
            <Typography variant="h5" sx={{ color: "#111111", fontWeight: 700 }}>
              {allowance.remaining} / {allowance.limit}
            </Typography>
          </Paper>
        )}
        {items.map(([key, label, color]) => (
          <Paper variant="outlined" key={key} sx={{ p: 2, bgcolor: "#ffffff", border: "1px solid rgba(0, 0, 0, 0.06)", borderRadius: "21.6px" }}>
            <Typography variant="caption" color="text.secondary">
              {label}
            </Typography>
            <Typography variant="h5" sx={{ color, fontWeight: 700 }}>
              {allowance[key]}
            </Typography>
          </Paper>
        ))}
      </Box>
      <Alert severity="info" sx={{ borderRadius: "14px" }}>{allowance.notice}</Alert>
    </Box>
  );
}
