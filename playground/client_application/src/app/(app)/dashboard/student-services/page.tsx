import type { Metadata } from "next";

import { InstitutionView } from "../institution-view";

export const metadata: Metadata = { title: { absolute: "Near Completers Tool" } };

export default function StudentServicesPage() {
  return <InstitutionView view="student-services" />;
}
