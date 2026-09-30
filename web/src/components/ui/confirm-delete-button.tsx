import { Button, Dialog, Portal, Stack, Text } from "@chakra-ui/react";
import { useState } from "react";

export type ConfirmDeleteButtonProps = {
  /** The trigger's text — "Delete book". */
  label: string;
  /** What is about to be deleted, named so the confirmation is specific. */
  subject: string;
  /** What the deletion takes with it, in plain words. */
  consequences: string;
  isPending: boolean;
  /** Resolves once the deletion succeeded; the dialog stays open on a rejection. */
  onConfirm: () => Promise<unknown>;
};

/**
 * A destructive action behind a confirmation. The dialog names the thing being
 * deleted and what goes with it, and stays open if the request fails so the
 * error toast and a retry are both one click away.
 */
export const ConfirmDeleteButton = ({
  label,
  subject,
  consequences,
  isPending,
  onConfirm,
}: ConfirmDeleteButtonProps) => {
  // States.
  const [open, setOpen] = useState(false);

  const confirm = async () => {
    try {
      await onConfirm();
      setOpen(false);
    } catch {
      // The caller raises the error toast; keep the dialog for a retry.
    }
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(details) => {
        if (!isPending) { setOpen(details.open); }
      }}
      role="alertdialog"
    >
      <Dialog.Trigger asChild>
        <Button
          size="sm"
          variant="outline"
          borderColor="status.err"
          color="status.err"
          borderRadius="md"
          _hover={{ bg: "bg.sunken" }}
        >
          {label}
        </Button>
      </Dialog.Trigger>
      <Portal>
        <Dialog.Backdrop />
        <Dialog.Positioner>
          <Dialog.Content bg="bg.surface" maxW="28rem" borderRadius="lg">
            <Dialog.Header>
              <Dialog.Title textStyle="subheading" color="fg">
                Delete {subject}?
              </Dialog.Title>
            </Dialog.Header>
            <Dialog.Body>
              <Stack gap="2">
                <Text textStyle="body" color="fg">{consequences}</Text>
                <Text textStyle="small" color="fg.muted">This cannot be undone.</Text>
              </Stack>
            </Dialog.Body>
            <Dialog.Footer gap="2">
              <Dialog.ActionTrigger asChild>
                <Button size="sm" variant="ghost" color="fg.muted" disabled={isPending}>
                  Cancel
                </Button>
              </Dialog.ActionTrigger>
              <Button
                size="sm"
                bg="status.err"
                color="accent.contrast"
                borderRadius="md"
                loading={isPending}
                loadingText="Deleting…"
                _hover={{ opacity: 0.9 }}
                onClick={() => void confirm()}
              >
                Delete
              </Button>
            </Dialog.Footer>
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  );
};
