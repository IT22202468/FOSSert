import { useEffect, useState } from "react";
import {
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  Link,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import BlockRoundedIcon from "@mui/icons-material/BlockRounded";
import { getAdminToken } from "../api";
import type { Participant, Status } from "../types";

const color: Record<
  Status,
  "default" | "primary" | "success" | "error" | "warning"
> = {
  PENDING: "default",
  SENDING: "primary",
  SENT: "success",
  FAILED: "error",
  UNCERTAIN: "warning",
};

function updatedLabel(participant: Participant) {
  if (participant.status === "PENDING" || !participant.updated_at) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(participant.updated_at));
}

function EditableParticipant({
  participant,
  onPatch,
}: {
  participant: Participant;
  onPatch: (id: string, data: Record<string, unknown>) => Promise<void>;
}) {
  const [name, setName] = useState(participant.name),
    [email, setEmail] = useState(participant.email),
    [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">(
      "idle",
    );
  const locked = ["SENT", "SENDING", "UNCERTAIN"].includes(participant.status);
  useEffect(() => {
    setName(participant.name);
    setEmail(participant.email);
  }, [participant.name, participant.email]);
  const save = async (field: "name" | "email") => {
    const value = field === "name" ? name : email;
    if (value === participant[field]) return;
    setSaveState("saving");
    try {
      await onPatch(participant.id, { [field]: value });
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  };
  const keySave = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.currentTarget.blur();
    }
  };
  return (
    <>
      <TableCell padding="checkbox">
        <Tooltip
          title={
            participant.is_excluded
              ? "Include participant"
              : "Exclude participant"
          }
        >
          <Checkbox
            checked={!participant.is_excluded}
            onChange={async (event) => {
              setSaveState("saving");
              try {
                await onPatch(participant.id, {
                  is_excluded: !event.target.checked,
                });
                setSaveState("saved");
              } catch {
                setSaveState("error");
              }
            }}
          />
        </Tooltip>
      </TableCell>
      <TableCell>
        <TextField
          variant="standard"
          value={name}
          disabled={locked}
          error={!name.trim()}
          onChange={(event) => {
            setName(event.target.value);
            setSaveState("idle");
          }}
          onBlur={() => void save("name")}
          onKeyDown={keySave}
          inputProps={{ "aria-label": `Name for ${participant.email}` }}
        />
      </TableCell>
      <TableCell>
        <TextField
          variant="standard"
          type="email"
          value={email}
          disabled={locked}
          error={!participant.is_valid}
          onChange={(event) => {
            setEmail(event.target.value);
            setSaveState("idle");
          }}
          onBlur={() => void save("email")}
          onKeyDown={keySave}
          inputProps={{
            "aria-label": `Email for ${participant.name || "participant"}`,
          }}
        />
      </TableCell>
      <TableCell>
        <Stack spacing={0.5} alignItems="flex-start">
          {participant.is_excluded ? (
            <Chip size="small" label="Excluded" />
          ) : participant.is_valid ? (
            <Chip
              size="small"
              color="success"
              variant="outlined"
              label="Valid"
            />
          ) : (
            <Chip size="small" color="error" label="Invalid" />
          )}
          {participant.validation_error && (
            <Typography variant="caption" color="error">
              {participant.validation_error}
            </Typography>
          )}
          {participant.previous_delivery && (
            <Chip
              size="small"
              color="warning"
              variant="outlined"
              label="Previously sent"
            />
          )}
          {saveState !== "idle" && (
            <Typography
              variant="caption"
              color={
                saveState === "error"
                  ? "error"
                  : saveState === "saved"
                    ? "success.main"
                    : "text.secondary"
              }
            >
              {saveState === "saving"
                ? "Saving…"
                : saveState === "saved"
                  ? "Saved"
                  : "Save failed"}
            </Typography>
          )}
        </Stack>
      </TableCell>
    </>
  );
}

export default function ParticipantTable({
  rows,
  onPatch,
  onReconcile,
  onRevoke,
  onReactivate,
}: {
  rows: Participant[];
  onPatch?: (id: string, data: Record<string, unknown>) => Promise<void>;
  onReconcile?: (
    id: string,
    action: "CONFIRM_SENT" | "CONFIRM_NOT_SENT",
  ) => void;
  onRevoke?: (id: string, reason?: string) => Promise<void>;
  onReactivate?: (id: string) => Promise<void>;
}) {
  const [revokeTarget, setRevokeTarget] = useState<Participant | null>(null);
  const [revokeReason, setRevokeReason] = useState("");
  const [revoking, setRevoking] = useState(false);

  const [reactivateTarget, setReactivateTarget] = useState<Participant | null>(null);
  const [reactivating, setReactivating] = useState(false);
  return (
    <>
    <TableContainer
      component={Paper}
      variant="outlined"
      sx={{ maxHeight: 520, borderRadius: "21.6px", bgcolor: "#ffffff", border: "1px solid rgba(0, 0, 0, 0.06)", overflowX: "auto" }}
    >
      <Table stickyHeader size="small">
        <TableHead>
          <TableRow>
            {onPatch && <TableCell padding="checkbox">Use</TableCell>}
            <TableCell>Participant</TableCell>
            <TableCell>Email</TableCell>
            <TableCell>Validation</TableCell>
            <TableCell>Certificate ID</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Updated</TableCell>
            <TableCell>Attempt</TableCell>
            {onReconcile && <TableCell>Reconcile</TableCell>}
            <TableCell align="right">PDF</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={10} align="center" sx={{ py: 7 }}>
                <Typography fontWeight={700}>No participants to show</Typography>
                <Typography variant="body2" color="text.secondary">
                  Import a CSV or adjust the current search and filters.
                </Typography>
              </TableCell>
            </TableRow>
          )}
          {rows.map((participant) => (
            <TableRow key={participant.id} hover>
              {onPatch ? (
                <EditableParticipant
                  participant={participant}
                  onPatch={onPatch}
                />
              ) : (
                <>
                  <TableCell>{participant.name || <em>Missing</em>}</TableCell>
                  <TableCell>
                    {participant.email ? (
                      <Link href={`mailto:${participant.email}`}>
                        {participant.email}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell>
                    <Stack spacing={0.5} alignItems="flex-start">
                      {participant.is_valid ? (
                        <Chip
                          size="small"
                          color="success"
                          variant="outlined"
                          label="Valid"
                        />
                      ) : (
                        <Tooltip title={participant.validation_error || ""}>
                          <Chip size="small" color="error" label="Invalid" />
                        </Tooltip>
                      )}
                      {participant.previous_delivery && (
                        <Chip
                          size="small"
                          color="warning"
                          variant="outlined"
                          label="Previously sent"
                        />
                      )}
                      {participant.generation_error && (
                        <Tooltip title={participant.generation_error}>
                          <Chip
                            size="small"
                            color="error"
                            variant="outlined"
                            label="Generation failed"
                          />
                        </Tooltip>
                      )}
                    </Stack>
                  </TableCell>
                </>
              )}
              <TableCell sx={{ minWidth: 150 }}>
                {participant.certificate_code ? (
                  <Tooltip title="View in Certificate Verification Portal">
                    <Link
                      href={`?code=${encodeURIComponent(participant.certificate_code)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      sx={{
                        fontFamily: "monospace",
                        fontSize: "0.8rem",
                        fontWeight: 600,
                        color: "primary.light",
                        textDecoration: "none",
                        "&:hover": { textDecoration: "underline" },
                      }}
                    >
                      {participant.certificate_code}
                    </Link>
                  </Tooltip>
                ) : (
                  "—"
                )}
              </TableCell>
              <TableCell>
                {participant.is_revoked ? (
                  <Stack direction="row" spacing={0.5} alignItems="center">
                    <Tooltip title={participant.revocation_reason ? `Revocation Reason: ${participant.revocation_reason}` : "Certificate revoked"}>
                      <Chip
                        size="small"
                        color="error"
                        label="REVOKED"
                        sx={{ fontWeight: 800, fontSize: "11px", letterSpacing: "0.05em" }}
                      />
                    </Tooltip>
                    {onReactivate && (
                      <Tooltip title="Restore / Reactivate Certificate">
                        <Button
                          size="small"
                          color="success"
                          variant="outlined"
                          onClick={() => setReactivateTarget(participant)}
                          sx={{ minWidth: 0, px: 1, py: 0.1, fontSize: "11px", borderRadius: "9999px" }}
                        >
                          Restore
                        </Button>
                      </Tooltip>
                    )}
                  </Stack>
                ) : (
                  <>
                    <Chip
                      size="small"
                      color={color[participant.status]}
                      label={participant.status}
                    />
                    {participant.error_reason && (
                      <Tooltip title={participant.error_reason}>
                        <InfoOutlinedIcon sx={{ fontSize: 16, ml: 0.5, verticalAlign: "middle", color: "text.secondary", cursor: "help" }} />
                      </Tooltip>
                    )}
                  </>
                )}
              </TableCell>
              <TableCell sx={{ whiteSpace: "nowrap" }}>
                {updatedLabel(participant)}
              </TableCell>
              <TableCell>
                {participant.attempts?.[0] ? (
                  <Tooltip
                    title={
                      participant.attempts[0].error_reason ||
                      `Delivery reference: ${participant.delivery_reference}`
                    }
                  >
                    <span>
                      #{participant.attempts[0].attempt_number}{" "}
                      {participant.attempts[0].outcome}
                    </span>
                  </Tooltip>
                ) : (
                  "—"
                )}
              </TableCell>
              {onReconcile && (
                <TableCell>
                  {participant.status === "UNCERTAIN" ? (
                    <Stack spacing={0.5} alignItems="flex-start">
                      <Button
                        size="small"
                        color="success"
                        onClick={() =>
                          onReconcile(participant.id, "CONFIRM_SENT")
                        }
                      >
                        Found in Sent
                      </Button>
                      <Button
                        size="small"
                        color="warning"
                        onClick={() =>
                          onReconcile(participant.id, "CONFIRM_NOT_SENT")
                        }
                      >
                        Not sent
                      </Button>
                      <Tooltip title="Use this reference when inspecting message details">
                        <code>{participant.delivery_reference.slice(-12)}</code>
                      </Tooltip>
                    </Stack>
                  ) : (
                    "—"
                  )}
                </TableCell>
              )}
              <TableCell align="right">
                <Stack direction="row" spacing={0.5} justifyContent="flex-end" alignItems="center">
                  {onRevoke && !participant.is_revoked && (participant.status === "SENT" || participant.filename || participant.certificate_code) && (
                    <Tooltip title="Invalidate / Revoke Certificate">
                      <IconButton
                        size="small"
                        color="error"
                        aria-label={`Revoke certificate for ${participant.name}`}
                        onClick={() => {
                          setRevokeTarget(participant);
                          setRevokeReason("Issued to incorrect recipient");
                        }}
                      >
                        <BlockRoundedIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                  {participant.filename && participant.certificate_current && !participant.is_revoked && (
                    <IconButton
                      aria-label={`Download ${participant.name}`}
                      component="a"
                      href={`/api/participants/${participant.id}/certificate${getAdminToken() ? `?token=${encodeURIComponent(getAdminToken()!)}` : ""}`}
                    >
                      <DownloadIcon />
                    </IconButton>
                  )}
                  {participant.is_revoked && (
                    <Tooltip title="Download blocked: Certificate has been revoked">
                      <Chip size="small" variant="outlined" color="error" label="Blocked" sx={{ height: 24, fontSize: "10px" }} />
                    </Tooltip>
                  )}
                  {participant.filename && !participant.certificate_current && !participant.is_revoked && (
                    <Tooltip title="Certificate styling changed; regenerate it">
                      <Chip size="small" color="warning" label="Outdated" />
                    </Tooltip>
                  )}
                </Stack>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>

    {/* Revocation Confirmation Dialog */}
    <Dialog
      open={Boolean(revokeTarget)}
      onClose={() => !revoking && setRevokeTarget(null)}
      maxWidth="sm"
      fullWidth
      slotProps={{ paper: { sx: { borderRadius: "21.6px", p: 1 } } }}
    >
      <DialogTitle sx={{ fontWeight: 800, color: "#991b1b" }}>
        Invalidate / Revoke Certificate
      </DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ color: "#111111", mb: 1.5, fontWeight: 500 }}>
          Are you sure you want to invalidate the certificate for{" "}
          <strong>{revokeTarget?.name}</strong>
          {revokeTarget?.certificate_code && (
            <>
              {" "}(<code>{revokeTarget.certificate_code}</code>)
            </>
          )}?
        </DialogContentText>
        <DialogContentText sx={{ color: "#777777", fontSize: "0.875rem", mb: 2 }}>
          Anyone attempting to verify this certificate on the public verification portal will see that it has been officially invalidated by the SLIIT FOSS Community authority. Direct PDF downloads will be blocked.
        </DialogContentText>
        <TextField
          autoFocus
          fullWidth
          size="small"
          label="Revocation Reason"
          value={revokeReason}
          onChange={(e) => setRevokeReason(e.target.value)}
          placeholder="e.g. Issued to incorrect recipient / clerical mistake"
          disabled={revoking}
          sx={{ mt: 1 }}
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button
          onClick={() => setRevokeTarget(null)}
          disabled={revoking}
          sx={{ borderRadius: "9999px", color: "#777777" }}
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          color="error"
          disabled={revoking}
          onClick={async () => {
            if (!revokeTarget || !onRevoke) return;
            setRevoking(true);
            try {
              await onRevoke(revokeTarget.id, revokeReason.trim() || undefined);
              setRevokeTarget(null);
            } finally {
              setRevoking(false);
            }
          }}
          sx={{ borderRadius: "9999px", px: 2.5 }}
        >
          {revoking ? "Revoking…" : "Invalidate Certificate"}
        </Button>
      </DialogActions>
    </Dialog>

    {/* Reactivate Confirmation Dialog */}
    <Dialog
      open={Boolean(reactivateTarget)}
      onClose={() => !reactivating && setReactivateTarget(null)}
      maxWidth="sm"
      fullWidth
      slotProps={{ paper: { sx: { borderRadius: "21.6px", p: 1 } } }}
    >
      <DialogTitle sx={{ fontWeight: 800, color: "#111111" }}>
        Reactivate Certificate
      </DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ color: "#111111", mb: 1, fontWeight: 500 }}>
          Are you sure you want to restore validity for{" "}
          <strong>{reactivateTarget?.name}</strong>
          {reactivateTarget?.certificate_code && (
            <>
              {" "}(<code>{reactivateTarget.certificate_code}</code>)
            </>
          )}?
        </DialogContentText>
        <DialogContentText sx={{ color: "#777777", fontSize: "0.875rem" }}>
          This will clear the revoked status and restore the certificate as an authentic, downloadable credential on the public verification registry.
        </DialogContentText>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button
          onClick={() => setReactivateTarget(null)}
          disabled={reactivating}
          sx={{ borderRadius: "9999px", color: "#777777" }}
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          color="success"
          disabled={reactivating}
          onClick={async () => {
            if (!reactivateTarget || !onReactivate) return;
            setReactivating(true);
            try {
              await onReactivate(reactivateTarget.id);
              setReactivateTarget(null);
            } finally {
              setReactivating(false);
            }
          }}
          sx={{ borderRadius: "9999px", px: 2.5 }}
        >
          {reactivating ? "Restoring…" : "Reactivate Certificate"}
        </Button>
      </DialogActions>
    </Dialog>
    </>
  );
}
