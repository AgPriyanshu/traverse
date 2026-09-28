import { Button, Dialog, HStack, Kbd, Portal, Stack, Text } from "@chakra-ui/react";

const GLOBAL_KEYS: [string, string][] = [
  ["j", "Next task"],
  ["k", "Previous task"],
  ["x", "Select for bulk accept"],
  ["u", "Undo last resolution"],
  ["?", "Toggle this legend"],
];

const TASK_KEYS: [string, string][] = [
  ["a", "Accept / confirm the primary action"],
  ["e", "Edit — change the predicate"],
  ["r", "Reject"],
  ["m", "Merge (merge tasks only)"],
  ["s", "Keep separate (merge tasks only)"],
  ["t", "Mark as a temporal transition (conflicts only)"],
  ["1–9", "Pick a specific relation / candidate by position"],
  ["c / p / o / n", "Classify: character / place / organisation / not an entity"],
];

export type ShortcutsOverlayProps = {
  open: boolean;
  onClose: () => void;
};

export const ShortcutsOverlay = ({ open, onClose }: ShortcutsOverlayProps) => {
  return (
    <Dialog.Root open={open} onOpenChange={(details) => { if (!details.open) { onClose(); } }}>
      <Portal>
        <Dialog.Backdrop />
        <Dialog.Positioner>
          <Dialog.Content bg="bg.surface" maxW="26rem" borderRadius="lg">
            <Dialog.Header borderBottomWidth="1px" borderColor="border">
              <Dialog.Title textStyle="subheading" color="fg">Keyboard shortcuts</Dialog.Title>
            </Dialog.Header>
            <Dialog.Body>
              <Stack gap="4" paddingBlock="2">
                <Stack gap="2">
                  <Text textStyle="small" fontWeight="600" color="fg.muted">Anywhere</Text>
                  {GLOBAL_KEYS.map(([key, label]) => (
                    <HStack key={key} justify="space-between">
                      <Text textStyle="body" color="fg">{label}</Text>
                      <Kbd>{key}</Kbd>
                    </HStack>
                  ))}
                </Stack>

                <Stack gap="2">
                  <Text textStyle="small" fontWeight="600" color="fg.muted">On the active task</Text>
                  {TASK_KEYS.map(([key, label]) => (
                    <HStack key={key} justify="space-between" gap="4">
                      <Text textStyle="body" color="fg">{label}</Text>
                      <Kbd whiteSpace="nowrap">{key}</Kbd>
                    </HStack>
                  ))}
                </Stack>
              </Stack>
            </Dialog.Body>
            <Dialog.CloseTrigger asChild>
              <Button size="xs" variant="ghost" color="fg.muted" position="absolute" top="3" right="3">
                Close
              </Button>
            </Dialog.CloseTrigger>
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  );
};
