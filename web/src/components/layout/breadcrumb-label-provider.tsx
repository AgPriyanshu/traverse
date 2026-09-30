import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { BreadcrumbLabelContext } from "./breadcrumb-label";

/** Holds the name of the record a detail page is showing, which only that page has fetched. */
export const BreadcrumbLabelProvider = ({ children }: { children: ReactNode }) => {
  // States.
  const [label, setLabel] = useState<string | null>(null);

  // useMemos.
  const value = useMemo(() => ({ label, setLabel }), [label]);

  return <BreadcrumbLabelContext.Provider value={value}>{children}</BreadcrumbLabelContext.Provider>;
};
