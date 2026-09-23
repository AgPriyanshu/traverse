import { Box, Button, HStack, Stack, Text, chakra } from "@chakra-ui/react";
import type { Chapter, ImportanceTier, RelationFamily } from "@/lib/api";
import { TIER_LABEL, TIER_ORDER } from "../character-labels";
import { hasEdgeFilter } from "./graph-filters";
import type { GraphFilters } from "./graph-filters";
import { FamilyStroke } from "./family-stroke";
import { FAMILY_LABEL, FAMILY_ORDER } from "./relation-style";

const Select = chakra("select");

const toggle = <T,>(list: T[], item: T): T[] => {
  return list.includes(item) ? list.filter((entry) => entry !== item) : [...list, item];
};

export type GraphFilterBarProps = {
  filters: GraphFilters;
  chapters: readonly Chapter[];
  onChange: (next: GraphFilters) => void;
};

export const GraphFilterBar = ({ filters, chapters, onChange }: GraphFilterBarProps) => {
  // Variables.
  const numbered = chapters
    .filter((chapter) => chapter.number !== null && chapter.number !== undefined)
    .map((chapter) => chapter.number as number)
    .sort((a, b) => a - b);
  const isFiltered =
    hasEdgeFilter(filters) || filters.tiers.length > 0;

  const chapterSelect = (
    label: string,
    value: number | null,
    onPick: (value: number | null) => void,
  ) => (
    <Box as="label" display="flex" alignItems="center" gap="2">
      <Text as="span" textStyle="small" color="fg.muted">
        {label}
      </Text>
      <Select
        value={value === null ? "" : String(value)}
        onChange={(event) => {
          onPick(event.target.value === "" ? null : Number(event.target.value));
        }}
        textStyle="data"
        bg="bg.sunken"
        color="fg"
        borderWidth="1px"
        borderColor="border.control"
        borderRadius="md"
        paddingInline="2"
        paddingBlock="1"
      >
        <option value="">any</option>
        {numbered.map((number) => (
          <option key={number} value={number}>
            {number}
          </option>
        ))}
      </Select>
    </Box>
  );

  return (
    <Stack as="section" aria-label="Filters" gap="3">
      <HStack gap="2" wrap="wrap" role="group" aria-label="Relation family">
        {FAMILY_ORDER.map((family: RelationFamily) => {
          const on = filters.families.includes(family);
          return (
            <Button
              key={family}
              size="xs"
              variant="outline"
              aria-pressed={on}
              borderColor={on ? "accent.solid" : "border.control"}
              bg={on ? "accent.subtle" : "transparent"}
              color="fg"
              onClick={() => { onChange({ ...filters, families: toggle(filters.families, family) }); }}
            >
              <FamilyStroke family={family} width={20} />
              {FAMILY_LABEL[family]}
            </Button>
          );
        })}
      </HStack>

      <HStack gap="2" wrap="wrap" role="group" aria-label="Character importance">
        {TIER_ORDER.map((tier: ImportanceTier) => {
          const on = filters.tiers.includes(tier);
          return (
            <Button
              key={tier}
              size="xs"
              variant="outline"
              aria-pressed={on}
              borderColor={on ? "accent.solid" : "border.control"}
              bg={on ? "accent.subtle" : "transparent"}
              color="fg"
              onClick={() => { onChange({ ...filters, tiers: toggle(filters.tiers, tier) }); }}
            >
              {TIER_LABEL[tier]}
            </Button>
          );
        })}
      </HStack>

      <HStack gap="5" wrap="wrap" align="center">
        <Box as="label" display="flex" alignItems="center" gap="2">
          <Text as="span" textStyle="small" color="fg.muted">
            Minimum confidence
          </Text>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={filters.minConfidence}
            aria-valuetext={`${Math.round(filters.minConfidence * 100)} percent`}
            style={{ accentColor: "var(--chakra-colors-accent-solid)" }}
            onChange={(event) => {
              onChange({ ...filters, minConfidence: Number(event.target.value) });
            }}
          />
          <Text as="span" textStyle="data" color="fg" minWidth="10">
            {Math.round(filters.minConfidence * 100)}%
          </Text>
        </Box>
        {chapterSelect("Chapters from", filters.chapterFrom, (value) => {
          onChange({ ...filters, chapterFrom: value });
        })}
        {chapterSelect("to", filters.chapterTo, (value) => {
          onChange({ ...filters, chapterTo: value });
        })}
        {isFiltered ? (
          <Button
            size="xs"
            variant="ghost"
            color="accent.fg"
            onClick={() => {
              onChange({
                families: [],
                tiers: [],
                minConfidence: 0,
                chapterFrom: null,
                chapterTo: null,
              });
            }}
          >
            Clear filters
          </Button>
        ) : null}
      </HStack>
    </Stack>
  );
};
