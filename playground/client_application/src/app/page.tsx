import { redirect } from "next/navigation";

import { routes } from "@/lib/routes";

/** The app opens on the executive view. */
export default function HomePage() {
  redirect(routes.executive);
}
