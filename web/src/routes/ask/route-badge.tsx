import { Text } from "@chakra-ui/react";
import type { TurnRoute } from "./types";
import { ROUTE_LABEL } from "./route-labels";

export const RouteBadge = ({ route }: { route: TurnRoute }) => {
  return (
    <Text textStyle="small" color="fg.subtle">
      Answered from {ROUTE_LABEL[route.route]}
      {route.explanation ? ` — ${route.explanation}` : ""}
    </Text>
  );
};
