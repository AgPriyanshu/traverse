import {
  Box,
  Button,
  Field,
  HStack,
  NumberInput,
  Progress,
  Stack,
  Text,
  VisuallyHidden,
} from "@chakra-ui/react";
import { useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { useNavigate } from "react-router";
import { ErrorState } from "@/components/ui";
import { UploadIcon } from "@/components/ui/icons";
import type { UploadProgress } from "@/lib/api";
import { isAlreadyIngested, useUploadBook } from "@/lib/api";
import { MAX_UPLOAD_BYTES, validateUpload } from "@/routes/books/validate-upload";

export type AddBookFormProps = {
  projectId: string;
  /** The next open series slot — editable, since books may arrive in any order (S5.9). */
  suggestedOrder: number;
};

/**
 * Adding a book to an existing series without leaving the project screen.
 * `series_order` is prefilled but never locked — a reader may have the third
 * volume in hand before the second (S5.9).
 */
export const AddBookForm = ({ projectId, suggestedOrder }: AddBookFormProps) => {
  // States.
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [seriesOrder, setSeriesOrder] = useState(suggestedOrder);
  const [progress, setProgress] = useState<UploadProgress | null>(null);

  // Refs.
  const inputRef = useRef<HTMLInputElement>(null);

  // Hooks.
  const navigate = useNavigate();

  // Apis.
  const uploadBook = useUploadBook();

  // Variables.
  const canSubmit = file !== null && fileError === null && !uploadBook.isPending;

  // Handlers.
  const acceptFile = (candidate: File | undefined) => {
    if (!candidate) { return; }
    const message = validateUpload(candidate);
    setFileError(message);
    setFile(message === null ? candidate : null);
  };

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    acceptFile(event.target.files?.[0]);
  };

  const handleSubmit = async () => {
    if (!file || !canSubmit) { return; }
    setProgress(null);
    const result = await uploadBook.mutateAsync({
      projectId,
      file,
      seriesOrder,
      onProgress: setProgress,
    });

    setFile(null);
    setFileError(null);
    if (inputRef.current) { inputRef.current.value = ""; }

    const bookId = isAlreadyIngested(result) ? result.book_id : result.id;
    void navigate(`/books/${bookId}`);
  };

  return (
    <Stack gap="4" as="section" aria-label="Add a book to this project">
      <HStack gap="4" wrap="wrap" align="flex-end">
        <Field.Root flex="1" minWidth="14rem">
          <Field.Label textStyle="small" color="fg.muted">
            File
          </Field.Label>
          <Box
            asChild
            display="flex"
            alignItems="center"
            gap="2"
            cursor="pointer"
            borderWidth="1px"
            borderStyle="dashed"
            borderColor="border.control"
            bg="bg.sunken"
            borderRadius="md"
            paddingInline="3"
            paddingBlock="2"
            _hover={{ borderColor: "accent.solid" }}
          >
            <label htmlFor="add-book-file">
              <UploadIcon boxSize="4" color="fg.subtle" aria-hidden="true" />
              <Text textStyle="small" color="fg" truncate>
                {file ? file.name : `PDF only · up to ${MAX_UPLOAD_BYTES / (1024 * 1024)} MB`}
              </Text>
              <VisuallyHidden>
                <input
                  ref={inputRef}
                  id="add-book-file"
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={handleInputChange}
                />
              </VisuallyHidden>
            </label>
          </Box>
        </Field.Root>

        <Field.Root width="9rem">
          <Field.Label textStyle="small" color="fg.muted">
            Series order
          </Field.Label>
          <NumberInput.Root
            value={String(seriesOrder)}
            min={1}
            onValueChange={(details) => { setSeriesOrder(details.valueAsNumber || 1); }}
          >
            <NumberInput.Input
              borderColor="border.control"
              borderRadius="md"
              bg="bg.surface"
              textStyle="body"
            />
          </NumberInput.Root>
        </Field.Root>

        <Button
          bg="accent.solid"
          color="accent.contrast"
          borderRadius="md"
          disabled={!canSubmit}
          loading={uploadBook.isPending}
          loadingText="Uploading"
          _hover={{ opacity: 0.9 }}
          onClick={() => void handleSubmit()}
        >
          Add book
        </Button>
      </HStack>

      {fileError ? (
        <Text role="alert" textStyle="small" color="status.err">
          {fileError}
        </Text>
      ) : null}

      {uploadBook.isPending ? (
        <Progress.Root value={progress ? Math.round(progress.percent) : null} maxW="measure">
          <HStack justify="space-between" gap="4">
            <Progress.Label textStyle="small" color="fg.muted">
              Uploading {file?.name}
            </Progress.Label>
            <Progress.ValueText textStyle="data" color="fg.subtle">
              {progress ? `${Math.round(progress.percent)}%` : "—"}
            </Progress.ValueText>
          </HStack>
          <Progress.Track bg="bg.sunken" borderRadius="full" height="1.5">
            <Progress.Range bg="accent.solid" borderRadius="full" />
          </Progress.Track>
        </Progress.Root>
      ) : null}

      {uploadBook.error ? (
        <ErrorState
          error={uploadBook.error}
          onRetry={() => void handleSubmit()}
          title="Upload did not start"
        />
      ) : null}
    </Stack>
  );
};
