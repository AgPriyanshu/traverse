import { Button, Field, Input, NativeSelect, Stack } from "@chakra-ui/react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { PageHeader } from "@/components/layout";
import { ErrorState } from "@/components/ui";
import type { ProjectKind } from "@/lib/api";
import { useCreateProject } from "@/lib/api";

/**
 * A standalone is a one-book project — the same code path as a series,
 * just never given a second book (S5.9). There is no separate flow for it.
 */
export const ProjectNew = () => {
  // States.
  const [name, setName] = useState("");
  const [kind, setKind] = useState<ProjectKind>("standalone");

  // Hooks.
  const navigate = useNavigate();

  // Apis.
  const createProject = useCreateProject();

  // Variables.
  const canSubmit = name.trim() !== "" && !createProject.isPending;

  // Handlers.
  const handleSubmit = async () => {
    if (!canSubmit) { return; }
    const project = await createProject.mutateAsync({ name: name.trim(), kind });
    void navigate(`/projects/${project.id}`);
  };

  return (
    <>
      <PageHeader
        title="New project"
        description="Name it, choose whether it holds one novel or a series, then add books to it."
      />

      <Stack gap="6" maxW="measure">
        <Field.Root>
          <Field.Label textStyle="small" color="fg.muted">
            Project name
          </Field.Label>
          <Input
            value={name}
            placeholder="Anne of Green Gables"
            borderColor="border.control"
            borderRadius="md"
            bg="bg.surface"
            textStyle="body"
            onChange={(event) => { setName(event.target.value); }}
          />
        </Field.Root>

        <Field.Root>
          <Field.Label textStyle="small" color="fg.muted">
            Kind
          </Field.Label>
          <NativeSelect.Root size="sm" maxW="16rem">
            <NativeSelect.Field
              value={kind}
              borderColor="border.control"
              borderRadius="md"
              bg="bg.surface"
              onChange={(event) => { setKind(event.target.value as ProjectKind); }}
            >
              <option value="standalone">Standalone novel</option>
              <option value="series">Series</option>
            </NativeSelect.Field>
            <NativeSelect.Indicator />
          </NativeSelect.Root>
        </Field.Root>

        <Button
          bg="accent.solid"
          color="accent.contrast"
          borderRadius="md"
          alignSelf="flex-start"
          disabled={!canSubmit}
          loading={createProject.isPending}
          loadingText="Creating"
          _hover={{ opacity: 0.9 }}
          onClick={() => void handleSubmit()}
        >
          Create project
        </Button>

        {createProject.error ? (
          <ErrorState
            error={createProject.error}
            onRetry={() => void handleSubmit()}
            title="Could not create the project"
          />
        ) : null}
      </Stack>
    </>
  );
};

export default ProjectNew;
