import {
  Box,
  Button,
  Field,
  HStack,
  Heading,
  Input,
  NativeSelect,
  Stack,
  Text,
  VisuallyHidden,
} from "@chakra-ui/react";
import { useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { useNavigate } from "react-router";
import { PageHeader } from "@/components/layout";
import { ErrorState, LoadingSkeleton } from "@/components/ui";
import { UploadIcon } from "@/components/ui/icons";
import type { ProjectKind } from "@/lib/api";
import { useCreateProject, useProjects, useUploadBook } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { MAX_UPLOAD_BYTES, validateUpload } from "./validate-upload";

type Destination = "existing" | "new";

const SectionHeading = ({
  step,
  title,
}: {
  step: number;
  title: string;
}) => {
  return (
    <HStack gap="3" align="baseline">
      <Text textStyle="data" color="fg.subtle">
        {step}
      </Text>
      <Heading as="h2" textStyle="subheading">
        {title}
      </Heading>
    </HStack>
  );
};

export const Upload = () => {
  // States.
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [destination, setDestination] = useState<Destination>("new");
  const [projectId, setProjectId] = useState("");
  const [projectName, setProjectName] = useState("");
  const [projectKind, setProjectKind] = useState<ProjectKind>("standalone");

  // Refs.
  const inputRef = useRef<HTMLInputElement>(null);

  // Hooks.
  const navigate = useNavigate();

  // Apis.
  const projects = useProjects();
  const createProject = useCreateProject();
  const uploadBook = useUploadBook();

  // Variables.
  const submitError = uploadBook.error ?? createProject.error;
  const canSubmit =
    file !== null &&
    fileError === null &&
    (destination === "existing" ? projectId !== "" : projectName.trim() !== "");
  const isSubmitting = uploadBook.isPending || createProject.isPending;

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

  const handleDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    setIsDragging(false);
    acceptFile(event.dataTransfer.files?.[0]);
  };

  const handleDragOver = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleClear = () => {
    setFile(null);
    setFileError(null);
    if (inputRef.current) { inputRef.current.value = ""; }
  };

  const handleSubmit = async () => {
    if (!file || !canSubmit) { return; }

    let targetProjectId = projectId;

    if (destination === "new") {
      const project = await createProject.mutateAsync({
        name: projectName.trim(),
        kind: projectKind,
      });
      targetProjectId = project.id;
    }

    const book = await uploadBook.mutateAsync({
      projectId: targetProjectId,
      file,
    });
    void navigate(`/books/${book.id}`);
  };

  return (
    <>
      <PageHeader
        title="Add a book"
        description="A PDF of a novel. Traverse parses it, keeps the page each passage came from, and builds the cast from there."
      />

      <Stack gap="9" maxW="measure">
        <Stack gap="4">
          <SectionHeading step={1} title="Choose a file" />

          <Box
            asChild
            display="block"
            cursor="pointer"
            borderWidth="1px"
            borderStyle="dashed"
            borderColor={isDragging ? "accent.solid" : "border.control"}
            bg={isDragging ? "accent.subtle" : "bg.sunken"}
            borderRadius="lg"
            paddingBlock="10"
            paddingInline="5"
            textAlign="center"
            transitionProperty="border-color, background-color"
            transitionDuration="fast"
            _hover={{ borderColor: "accent.solid" }}
            _focusWithin={{
              outline: "2px solid",
              outlineColor: "accent.focusRing",
              outlineOffset: "2px",
            }}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            <label htmlFor="book-file">
              <Stack gap="2" align="center">
                <UploadIcon boxSize="6" color="fg.subtle" aria-hidden="true" />
                <Text textStyle="body" color="fg">
                  Drop a PDF here, or choose a file
                </Text>
                <Text textStyle="data" color="fg.subtle">
                  PDF only · up to {formatBytes(MAX_UPLOAD_BYTES)}
                </Text>
              </Stack>

              <VisuallyHidden>
                <input
                  ref={inputRef}
                  id="book-file"
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={handleInputChange}
                />
              </VisuallyHidden>
            </label>
          </Box>

          {fileError ? (
            <Text role="alert" textStyle="small" color="status.err">
              {fileError}
            </Text>
          ) : null}

          {file ? (
            <HStack
              justify="space-between"
              gap="4"
              borderWidth="1px"
              borderColor="border"
              borderRadius="md"
              bg="bg.surface"
              paddingInline="4"
              paddingBlock="3"
            >
              <Stack gap="0.5" minWidth="0">
                <Text textStyle="body" color="fg" truncate>
                  {file.name}
                </Text>
                <Text textStyle="data" color="fg.subtle">
                  {formatBytes(file.size)}
                </Text>
              </Stack>
              <Button
                size="xs"
                variant="ghost"
                color="fg.muted"
                onClick={handleClear}
              >
                Remove
              </Button>
            </HStack>
          ) : null}
        </Stack>

        <Stack gap="4">
          <SectionHeading step={2} title="Choose where it goes" />
          <Text textStyle="small" color="fg.muted">
            A book belongs to a project. A standalone project holds one novel; a
            series holds several, and Traverse reconciles the cast across them.
          </Text>

          <HStack gap="2">
            <Button
              size="sm"
              variant={destination === "new" ? "solid" : "outline"}
              bg={destination === "new" ? "accent.solid" : "transparent"}
              color={destination === "new" ? "accent.contrast" : "fg.muted"}
              borderColor="border.control"
              borderRadius="md"
              aria-pressed={destination === "new"}
              onClick={() => setDestination("new")}
            >
              New project
            </Button>
            <Button
              size="sm"
              variant={destination === "existing" ? "solid" : "outline"}
              bg={destination === "existing" ? "accent.solid" : "transparent"}
              color={destination === "existing" ? "accent.contrast" : "fg.muted"}
              borderColor="border.control"
              borderRadius="md"
              aria-pressed={destination === "existing"}
              onClick={() => setDestination("existing")}
            >
              Existing project
            </Button>
          </HStack>

          {destination === "new" ? (
            <Stack gap="4">
              <Field.Root>
                <Field.Label textStyle="small" color="fg.muted">
                  Project name
                </Field.Label>
                <Input
                  value={projectName}
                  placeholder="Pride and Prejudice"
                  borderColor="border.control"
                  borderRadius="md"
                  bg="bg.surface"
                  textStyle="body"
                  onChange={(event) => setProjectName(event.target.value)}
                />
              </Field.Root>

              <Field.Root>
                <Field.Label textStyle="small" color="fg.muted">
                  Kind
                </Field.Label>
                <NativeSelect.Root size="sm">
                  <NativeSelect.Field
                    value={projectKind}
                    borderColor="border.control"
                    borderRadius="md"
                    bg="bg.surface"
                    onChange={(event) =>
                      setProjectKind(event.target.value as ProjectKind)
                    }
                  >
                    <option value="standalone">Standalone novel</option>
                    <option value="series">Series</option>
                  </NativeSelect.Field>
                  <NativeSelect.Indicator />
                </NativeSelect.Root>
              </Field.Root>
            </Stack>
          ) : null}

          {destination === "existing" && projects.isPending ? (
            <LoadingSkeleton variant="rows" count={1} label="Loading projects" />
          ) : null}

          {destination === "existing" && projects.error ? (
            <ErrorState
              error={projects.error}
              onRetry={() => void projects.refetch()}
              title="Existing projects are unavailable"
            />
          ) : null}

          {destination === "existing" && projects.data ? (
            <Field.Root>
              <Field.Label textStyle="small" color="fg.muted">
                Project
              </Field.Label>
              <NativeSelect.Root size="sm">
                <NativeSelect.Field
                  value={projectId}
                  borderColor="border.control"
                  borderRadius="md"
                  bg="bg.surface"
                  onChange={(event) => setProjectId(event.target.value)}
                >
                  <option value="">Choose a project…</option>
                  {projects.data.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </NativeSelect.Field>
                <NativeSelect.Indicator />
              </NativeSelect.Root>
            </Field.Root>
          ) : null}
        </Stack>

        <Stack gap="4">
          <Box>
            <Button
              bg="accent.solid"
              color="accent.contrast"
              borderRadius="md"
              disabled={!canSubmit || isSubmitting}
              loading={isSubmitting}
              loadingText="Uploading"
              _hover={{ opacity: 0.9 }}
              onClick={() => void handleSubmit()}
            >
              Start ingestion
            </Button>
          </Box>

          {submitError ? (
            <ErrorState error={submitError} title="Upload did not start" />
          ) : null}
        </Stack>
      </Stack>
    </>
  );
};

export default Upload;
