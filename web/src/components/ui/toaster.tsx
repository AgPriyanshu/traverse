import { Portal, Stack, Toast, Toaster as ChakraToaster } from "@chakra-ui/react";
import { TOAST_TONE_COLOR, toaster } from "./toaster-instance";

/** Mounted once in the app shell. Styled from tokens, never a Chakra colour scale. */
export const AppToaster = () => {
  return (
    <Portal>
      <ChakraToaster toaster={toaster} insetInline={{ mdDown: "4" }}>
        {(toast) => (
          <Toast.Root
            width={{ md: "sm" }}
            bg="bg.surface"
            borderWidth="1px"
            borderColor="border"
            borderRadius="lg"
            boxShadow="raised"
            paddingInline="4"
            paddingBlock="3"
          >
            <Toast.Indicator color={TOAST_TONE_COLOR[toast.type ?? "info"] ?? "fg"} />
            <Stack gap="0.5" flex="1" maxWidth="100%">
              {toast.title ? (
                <Toast.Title textStyle="body" color="fg" fontWeight="500">
                  {toast.title}
                </Toast.Title>
              ) : null}
              {toast.description ? (
                <Toast.Description textStyle="small" color="fg.muted">
                  {toast.description}
                </Toast.Description>
              ) : null}
            </Stack>
            {toast.action ? (
              <Toast.ActionTrigger textStyle="small" color="accent.fg">
                {toast.action.label}
              </Toast.ActionTrigger>
            ) : null}
            {toast.closable ? <Toast.CloseTrigger /> : null}
          </Toast.Root>
        )}
      </ChakraToaster>
    </Portal>
  );
};
