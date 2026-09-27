import { Box, Button, HStack, Stack, Text, chakra } from "@chakra-ui/react";
import type { Book, ImportanceTier, RelationFamily } from "@/lib/api";
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
  books: readonly Book[];
  onChange: (next: GraphFilters) => void;
};

/** A book filter slices the standing graph to one volume's view — animated in place, never a fresh graph (S5.11). */
export const GraphFilterBar = ({ filters, books, onChange }: GraphFilterBarProps) => {
  // Variables.
  const isFiltered = hasEdgeFilter(filters) || filters.tiers.length > 0;

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

        {books.length > 1 ? (
          <Box as="label" display="flex" alignItems="center" gap="2">
            <Text as="span" textStyle="small" color="fg.muted">
              Book
            </Text>
            <Select
              value={filters.bookFilter === null ? "" : String(filters.bookFilter)}
              onChange={(event) => {
                onChange({
                  ...filters,
                  bookFilter: event.target.value === "" ? null : Number(event.target.value),
                });
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
              <option value="">every book</option>
              {books.map((book) => (
                <option key={book.id} value={book.series_order ?? ""}>
                  {book.series_order ?? "?"}. {book.title}
                </option>
              ))}
            </Select>
          </Box>
        ) : null}

        {isFiltered ? (
          <Button
            size="xs"
            variant="ghost"
            color="accent.fg"
            onClick={() => {
              onChange({ families: [], tiers: [], minConfidence: 0, bookFilter: null });
            }}
          >
            Clear filters
          </Button>
        ) : null}
      </HStack>
    </Stack>
  );
};
