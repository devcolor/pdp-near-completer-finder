import type { Metadata } from "next";

import { InstitutionView } from "../institution-view";

export const metadata: Metadata = { title: "Financial hold" };

export default function FinancialAidPage() {
  return <InstitutionView view="financial" />;
}
