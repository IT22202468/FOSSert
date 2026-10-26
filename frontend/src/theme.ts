import { createTheme } from "@mui/material/styles";

export const tokens = {
  font: {
    primary: '"Inter", "Inter Fallback", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    base: "16px",
    lineHeightBase: "24px",
    scale: {
      xs: "11.2px",
      sm: "12px",
      md: "14px",
      lg: "16px",
      xl: "18px",
      "2xl": "30px",
      "3xl": "48px",
      "4xl": "72px",
    },
  },
  color: {
    text: {
      primary: "#111111",
      secondary: "#777777",
      tertiary: "#333333",
      inverse: "#999999",
    },
    surface: {
      muted: "#fafafa",
      raised: "#ffffff",
    },
    border: {
      default: "#000000",
      muted: "rgba(0, 0, 0, 0.06)",
      strong: "#eeeeee",
    },
    focus: {
      ring: "rgba(59, 130, 246, 0.5)",
    },
    brand: {
      primary: "#dc2626",
      hover: "#b91c1c",
      active: "#991b1b",
    },
    status: {
      success: "#16a34a",
      warning: "#d97706",
      error: "#dc2626",
    },
  },
  radius: {
    xs: "21.6px",
    sm: "136px",
    md: "16777200px", // Full pill
  },
  space: {
    1: "4px",
    2: "6px",
    3: "10px",
    4: "12px",
    5: "16px",
    6: "20px",
    7: "24px",
    8: "32px",
  },
  motion: {
    instant: "150ms",
    fast: "200ms",
    normal: "300ms",
    slow: "500ms",
  },
};

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: tokens.color.brand.primary,
      light: "#ef4444",
      dark: tokens.color.brand.hover,
      contrastText: "#ffffff",
    },
    secondary: {
      main: tokens.color.text.primary,
      contrastText: "#ffffff",
    },
    success: {
      main: tokens.color.status.success,
    },
    warning: {
      main: tokens.color.status.warning,
    },
    error: {
      main: tokens.color.status.error,
    },
    background: {
      default: tokens.color.surface.muted,
      paper: tokens.color.surface.raised,
    },
    text: {
      primary: tokens.color.text.primary,
      secondary: tokens.color.text.secondary,
    },
    divider: tokens.color.border.muted,
  },
  typography: {
    fontFamily: tokens.font.primary,
    fontSize: 16,
    h1: {
      fontSize: tokens.font.scale["4xl"],
      fontWeight: 800,
      lineHeight: 1.1,
      letterSpacing: "-0.03em",
      color: tokens.color.text.primary,
    },
    h2: {
      fontSize: tokens.font.scale["3xl"],
      fontWeight: 800,
      lineHeight: 1.15,
      letterSpacing: "-0.025em",
      color: tokens.color.text.primary,
    },
    h3: {
      fontSize: tokens.font.scale["2xl"],
      fontWeight: 700,
      lineHeight: 1.2,
      letterSpacing: "-0.02em",
      color: tokens.color.text.primary,
    },
    h4: {
      fontSize: tokens.font.scale.xl,
      fontWeight: 700,
      lineHeight: 1.3,
      letterSpacing: "-0.015em",
      color: tokens.color.text.primary,
    },
    h5: {
      fontSize: tokens.font.scale.lg,
      fontWeight: 600,
      lineHeight: 1.4,
      color: tokens.color.text.primary,
    },
    h6: {
      fontSize: tokens.font.scale.lg,
      fontWeight: 700,
      lineHeight: 1.4,
      color: tokens.color.text.primary,
    },
    body1: {
      fontSize: tokens.font.scale.lg,
      lineHeight: tokens.font.lineHeightBase,
      color: tokens.color.text.primary,
    },
    body2: {
      fontSize: tokens.font.scale.md,
      lineHeight: "20px",
      color: tokens.color.text.secondary,
    },
    caption: {
      fontSize: tokens.font.scale.sm,
      lineHeight: "16px",
      color: tokens.color.text.secondary,
    },
    overline: {
      fontSize: tokens.font.scale.xs,
      fontWeight: 700,
      letterSpacing: "0.1em",
      textTransform: "uppercase",
      color: tokens.color.brand.primary,
    },
    button: {
      fontFamily: tokens.font.primary,
      fontWeight: 600,
      textTransform: "none",
    },
  },
  shape: {
    borderRadius: 16,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: tokens.color.surface.muted,
          color: tokens.color.text.primary,
          fontFamily: tokens.font.primary,
        },
      },
    },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: {
          backgroundImage: "none",
          backgroundColor: tokens.color.surface.raised,
          border: `1px solid ${tokens.color.border.muted}`,
          borderRadius: tokens.radius.xs,
          boxShadow: "0 4px 20px rgba(0, 0, 0, 0.04)",
        },
      },
    },
    MuiCard: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: {
          backgroundColor: tokens.color.surface.raised,
          border: `1px solid ${tokens.color.border.muted}`,
          borderRadius: tokens.radius.xs,
          boxShadow: "0 2px 12px rgba(0, 0, 0, 0.03)",
          transition: `transform ${tokens.motion.fast} ease, box-shadow ${tokens.motion.fast} ease, border-color ${tokens.motion.fast} ease`,
          "&:hover": {
            transform: "translateY(-2px)",
            boxShadow: "0 8px 24px rgba(0, 0, 0, 0.06)",
            borderColor: tokens.color.border.strong,
          },
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          minHeight: 42,
          paddingInline: 22,
          textTransform: "none",
          borderRadius: 9999, // Pill geometry
          fontWeight: 600,
          fontSize: tokens.font.scale.md,
          transition: `all ${tokens.motion.fast} ease`,
          "&:focus-visible": {
            outline: `2px solid ${tokens.color.focus.ring}`,
            outlineOffset: 2,
          },
        },
        containedPrimary: {
          backgroundColor: tokens.color.brand.primary,
          color: "#ffffff",
          "&:hover": {
            backgroundColor: tokens.color.brand.hover,
            transform: "translateY(-1px)",
            boxShadow: "0 6px 18px rgba(220, 38, 38, 0.25)",
          },
          "&:active": {
            backgroundColor: tokens.color.brand.active,
            transform: "translateY(0)",
          },
          "&.Mui-disabled": {
            backgroundColor: "#f4f4f5",
            color: "#a1a1aa",
          },
        },
        containedSecondary: {
          backgroundColor: tokens.color.text.primary,
          color: "#ffffff",
          "&:hover": {
            backgroundColor: "#27272a",
          },
        },
        outlined: {
          borderColor: tokens.color.border.strong,
          color: tokens.color.text.primary,
          backgroundColor: "#ffffff",
          "&:hover": {
            borderColor: tokens.color.text.primary,
            backgroundColor: "#f4f4f5",
          },
          "&.Mui-disabled": {
            borderColor: tokens.color.border.strong,
            color: "#a1a1aa",
          },
        },
        text: {
          color: tokens.color.text.secondary,
          "&:hover": {
            color: tokens.color.text.primary,
            backgroundColor: "rgba(0, 0, 0, 0.04)",
          },
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          backgroundColor: tokens.color.surface.raised,
          transition: `border-color ${tokens.motion.fast} ease, box-shadow ${tokens.motion.fast} ease`,
          "& .MuiOutlinedInput-notchedOutline": {
            borderColor: tokens.color.border.strong,
          },
          "&:hover .MuiOutlinedInput-notchedOutline": {
            borderColor: tokens.color.text.primary,
          },
          "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
            borderColor: tokens.color.brand.primary,
            borderWidth: "1.5px",
          },
        },
        input: {
          color: tokens.color.text.primary,
          fontSize: tokens.font.scale.md,
        },
      },
    },
    MuiInputLabel: {
      styleOverrides: {
        root: {
          color: tokens.color.text.secondary,
          fontSize: tokens.font.scale.md,
          "&.Mui-focused": {
            color: tokens.color.brand.primary,
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 9999, // Pill chip
          fontWeight: 600,
          fontSize: tokens.font.scale.sm,
        },
        outlined: {
          borderColor: tokens.color.border.strong,
          backgroundColor: tokens.color.surface.raised,
          color: tokens.color.text.primary,
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 14,
          border: `1px solid ${tokens.color.border.strong}`,
          alignItems: "center",
          fontSize: tokens.font.scale.md,
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          backgroundColor: "#f4f4f5",
          borderRadius: 9999,
          height: 6,
        },
        bar: {
          borderRadius: 9999,
          backgroundColor: tokens.color.brand.primary,
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderColor: tokens.color.border.muted,
          color: tokens.color.text.primary,
          fontSize: tokens.font.scale.md,
        },
        head: {
          backgroundColor: tokens.color.surface.muted,
          color: tokens.color.text.secondary,
          fontWeight: 600,
          fontSize: tokens.font.scale.sm,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        },
      },
    },
  },
});
