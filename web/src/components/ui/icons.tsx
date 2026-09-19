import { Icon } from "@chakra-ui/react";
import type { ComponentProps, ReactNode } from "react";

type IconProps = Omit<ComponentProps<typeof Icon>, "children" | "asChild">;

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

/**
 * Chakra v3's `Icon` defaults to `asChild`, which drops its children straight
 * into the tree without an `<svg>` around them — React then warns that `path`
 * is an unrecognised tag. These icons own their `<svg>`, so it is turned off.
 */
const Glyph = ({ children, ...props }: IconProps & { children: ReactNode }) => {
  return (
    <Icon asChild={false} viewBox="0 0 24 24" {...props}>
      {children}
    </Icon>
  );
};

export const SunIcon = (props: IconProps) => {
  return (
    <Glyph {...props}>
      <g {...stroke}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </g>
    </Glyph>
  );
};

export const MoonIcon = (props: IconProps) => {
  return (
    <Glyph {...props}>
      <path {...stroke} d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
    </Glyph>
  );
};

export const BookIcon = (props: IconProps) => {
  return (
    <Glyph {...props}>
      <g {...stroke}>
        <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v16H6.5A2.5 2.5 0 0 0 4 20.5Z" />
        <path d="M4 20.5A2.5 2.5 0 0 1 6.5 18H20v4H6.5A2.5 2.5 0 0 1 4 20.5Z" />
      </g>
    </Glyph>
  );
};

export const UploadIcon = (props: IconProps) => {
  return (
    <Glyph {...props}>
      <g {...stroke}>
        <path d="M12 16V4" />
        <path d="m7 9 5-5 5 5" />
        <path d="M4 16v2.5A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5V16" />
      </g>
    </Glyph>
  );
};

export const GaugeIcon = (props: IconProps) => {
  return (
    <Glyph {...props}>
      <g {...stroke}>
        <path d="M4 18a8 8 0 1 1 16 0" />
        <path d="m12 14 4-4" />
      </g>
    </Glyph>
  );
};

export const ChevronLeftIcon = (props: IconProps) => {
  return (
    <Glyph {...props}>
      <path {...stroke} d="m15 5-7 7 7 7" />
    </Glyph>
  );
};

export const ChevronRightIcon = (props: IconProps) => {
  return (
    <Glyph {...props}>
      <path {...stroke} d="m9 5 7 7-7 7" />
    </Glyph>
  );
};
