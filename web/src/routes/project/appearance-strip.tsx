import { Box, HStack, Text } from "@chakra-ui/react";
import { formatSeriesOrderRun } from "@/lib/format";

export type AppearanceSlot = {
  seriesOrder: number;
  /** `undefined` renders a filled-but-unweighted mark — see the SCR note below. */
  intensity?: number;
  isFirst?: boolean;
};

export type AppearanceStripProps = {
  /** Every book slot in the project, in series order — filled or not. */
  totalSlots: number;
  slots: readonly AppearanceSlot[];
  characterName: string;
  size?: "sm" | "md";
};

const SLOT_GAP = 2;

/**
 * A per-book presence band: "appears in books 1, 2 and 5" is unreadable as
 * prose but is the single most useful fact about a character in a series
 * (design/DESIGN.md, S5.10). The coloured band is never the only channel —
 * a visible caption always prints the same fact as text, and every slot has
 * an individual accessible label besides.
 *
 * `intensity` (0–1, by mention count) is optional: `CharacterOut` (the
 * roster list contract) has no per-book mention count, only
 * `appears_in_books` presence, so the roster row renders every filled slot
 * at full, uniform intensity until that lands (SCR-1,
 * `plans/sprint-5/SCR.md`). The character detail page's own appearances
 * section has the real per-book count from `CharacterDetailOut.appearances`
 * and passes it through.
 */
export const AppearanceStrip = ({
  totalSlots,
  slots,
  characterName,
  size = "sm",
}: AppearanceStripProps) => {
  const bySlot = new Map(slots.map((slot) => [slot.seriesOrder, slot]));
  const dimension = size === "sm" ? 5 : 7;
  const present = slots.map((slot) => slot.seriesOrder);

  return (
    <Box>
      <HStack
        gap={`${SLOT_GAP}px`}
        role="img"
        aria-label={`${characterName} appears in ${
          present.length === 0 ? "no books" : `book${present.length === 1 ? "" : "s"} ${formatSeriesOrderRun(present)}`
        } of ${totalSlots}`}
      >
        {Array.from({ length: totalSlots }, (_unused, index) => {
          const seriesOrder = index + 1;
          const slot = bySlot.get(seriesOrder);
          const opacity = slot ? Math.max(0.35, slot.intensity ?? 1) : undefined;
          return (
            <Box
              key={seriesOrder}
              width={`${dimension * 3}px`}
              height={`${dimension}px`}
              borderRadius="sm"
              bg={slot ? "accent.solid" : "bg.sunken"}
              opacity={opacity}
              borderWidth={slot?.isFirst ? "2px" : "1px"}
              borderColor={slot?.isFirst ? "fg" : "border"}
              aria-hidden="true"
              title={`Book ${seriesOrder}${slot ? (slot.isFirst ? " — first appearance" : "") : " — not present"}`}
            />
          );
        })}
      </HStack>
      <Text textStyle="data" color="fg.subtle" marginBlockStart="0.5">
        {present.length === 0
          ? "not yet appeared"
          : `book${present.length === 1 ? "" : "s"} ${formatSeriesOrderRun(present)}`}
      </Text>
    </Box>
  );
};
