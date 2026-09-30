import { createContext, useContext, useEffect } from "react";

export type BreadcrumbLabelState = {
  label: string | null;
  setLabel: (label: string | null) => void;
};

export const BreadcrumbLabelContext = createContext<BreadcrumbLabelState>({
  label: null,
  setLabel: () => undefined,
});

export const useCurrentBreadcrumbLabel = (): string | null => {
  return useContext(BreadcrumbLabelContext).label;
};

/** Names the last breadcrumb after the record on screen, and clears it when the page unmounts. */
export const useBreadcrumbLabel = (label: string | null | undefined) => {
  // Context.
  const { setLabel } = useContext(BreadcrumbLabelContext);

  // useEffects.
  useEffect(() => {
    setLabel(label ?? null);
    return () => { setLabel(null); };
  }, [label, setLabel]);
};
