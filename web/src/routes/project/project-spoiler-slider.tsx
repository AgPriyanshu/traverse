import { ReadingPositionSlider } from "@/components/spoiler";
import { useReadingPositionContext } from "./reading-position-context";

export const ProjectSpoilerSlider = () => {
  // Context.
  const { index, maxIndex, label, isLimited, setIndex } = useReadingPositionContext();

  return (
    <ReadingPositionSlider
      index={index}
      maxIndex={maxIndex}
      label={label}
      isLimited={isLimited}
      onChange={setIndex}
    />
  );
};
